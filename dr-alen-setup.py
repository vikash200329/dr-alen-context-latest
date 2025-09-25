from .datasets.knowledge_context import get_kb_data
from .services import rank_received_results,extract_python_code,get_conversation_history,token_usage_calculator
from .alen_info import PERSISTENT_CLIENT, GEMINI_API_KEY
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from sentence_transformers import SentenceTransformer
import chromadb,json,asyncio
from langchain_core.messages import HumanMessage,SystemMessage
text_embedding_model=SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
client=chromadb.PersistentClient(path=PERSISTENT_CLIENT)
gemini_model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=GEMINI_API_KEY,
            temperature=0.8,
            max_output_tokens=2000
        )

def retrieve_KB_response(user_query,client=None,text_embedding_model=None):
    try:
        collection=client.get_collection(name="DR_ALEN_CONSUMPTION_1")
        user_input=text_embedding_model.encode(user_query)
        results=collection.query(query_embeddings=[user_input],n_results=1)
        rank_results=rank_received_results(documents=results,user_input=user_query)
        return rank_results
    except Exception as e:
        print("error in kb retrieve from llm_interaction_copy",str(e))
        return str(e)
    
# print(retrieve_KB_response("What is the maximum active power (KWT) for the meter 'TR 10 HT' yesterday?"))


async def retrieve_meter_names(query,company_id,top_k=20):
    fin_results=[]
    collection=client.get_collection('full_meter_names')
    query_embedding = text_embedding_model.encode(query, normalize_embeddings=True).tolist()
    where_clause={}
    if company_id is not None:
        where_clause['company_id']=company_id
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["metadatas", "distances"],
        where=where_clause if where_clause else None
    )
    for result in results['metadatas']:
        for action in result:
            if action['original_name'] not in fin_results:
                fin_results.append(action['original_name'])
    return fin_results

async def handle_llm_routing_action(user_query,model,token_calculator):

    try:
        # prompt = """
        # You are a smart query router that decides which LLM should handle an electrical meter query.

        # ## LLM Types:
        # - LLM_1: Handles consumption (kWh, kVAh), usage, shift analysis, and entity listing.
        # - LLM_2: Handles electrical readings (voltage, current, power, THD, PF, frequency, demand, KWH, real-time values, gateway status, data percentage/points, and communication status) to the electrical parameters.
        # - LLM_3: Handles queries related to Alarms


        # ## Examples:
        # "Yesterday's kWh consumption" → LLM_1
        # "List all meters" → LLM_1 (pure entity listing)
        # "Current voltage reading" → LLM_2
        # "List meters with max voltage" → LLM_2 (param-focused with entity context)
        # "Which meters not communicating" → LLM_2
        # "Show consumption and voltage data" → BOTH
        # "Peak demand and max voltage for all meters" -> LLM_2
        # "Show me all the meters with negative PF and negative KW" -> LLM_2
        # "energy/kw/kwhdel readings" -> LLM_2

        # ## Routing Logic:
        # - Route to LLM_1 for: energy totals, usage, consumption-only questions.
        # - Route to LLM_2 for: parameters, real-time readings, limits (min/max), communication issues,Gateway status,Data percentage.
        # - Route to LLM_3 for: Alarm related questions.
        # - Route to BOTH if the query mixes both (e.g., “consumption and voltage”).

        # ## Output Format:
        # {{
        # "routing_decision": "LLM_1" | "LLM_2" | "LLM_3" | "BOTH"
        # }}

        # Analyze this query and route it:
        # {user_question}

        # """
        prompt = """
        You are a smart query router that decides which LLM should handle an electrical meter query.

        ## LLM Types:
        - LLM_1: Handles consumption (kWh, kVAh), usage, shift analysis, and entity listing.
        - LLM_2: Handles electrical readings (voltage, current, power, THD, PF, frequency, demand, KWH, real-time values, gateway status, data percentage/points, communication status, and anomalies/spikes/abnormalities/unusual patterns) to the electrical parameters.
        - LLM_3: Handles queries related to Alarms

        ## Examples:
        "Yesterday's kWh consumption" → LLM_1
        "List all meters" → LLM_1 (pure entity listing)
        "Current voltage reading" → LLM_2
        "List meters with max voltage" → LLM_2 (param-focused with entity context)
        "Which meters not communicating" → LLM_2
        "Show consumption and voltage data" → BOTH
        "Peak demand and max voltage for all meters" → LLM_2
        "Show me all the meters with negative PF and negative KW" → LLM_2
        "Current kWh reading for meter 1" → LLM_2 (real-time reading)
        "Total kWh consumed yesterday" → LLM_1 (consumption analysis)
        "Voltage spikes in last week" → LLM_2
        "Energy anomalies today" → LLM_2
        "Unusual current patterns" → LLM_2

        ## Routing Logic:
        - Route to LLM_1 for:
        * Energy consumption analysis (kWh/kVAh consumed, usage patterns, totals)
        * Pure entity listing (without parameter context)
        * Shift-wise consumption analysis
        - Route to LLM_2 for:
        * Electrical parameters (voltage, current, power, THD, PF, frequency, energy/kwh/kwhdel readings)
        * Real-time readings (including current kWh values)
        * Data availability/percentage queries (highest priority)
        * Communication issues, Gateway status
        * Parameter limits (min/max values)
        * Anomalies/spikes/abnormalities/unusual patterns in electrical readings
        * Any electrical parameter queries (default for electrical data)
        - Route to LLM_3 for:
        * Alarm related questions
        - Route to BOTH if the query mixes consumption analysis with electrical parameters

        ## Key Decision Points:
        1. **Data Availability Queries**: Always route to LLM_2 (highest priority)
        2. **Anomaly Detection**: Always route to LLM_2 for spikes/abnormalities/unusual patterns
        3. **kWh Context**:
        - "kWh consumption/usage" → LLM_1
        - "current/real-time kWh reading" → LLM_2
        4. **Default Rule**: When uncertain about electrical parameters → LLM_2

        ## Output Format:
        {{
            "routing_decision": "LLM_1" | "LLM_2" | "LLM_3" | "BOTH"
        }}

        Analyze this query and route it:
        {user_question}
        """
        prompt_template=PromptTemplate(template=prompt,input_variables=['user_question'])
        model_load=prompt_template|model
        response=await asyncio.to_thread(model_load.invoke,{"user_question":user_query})
        raw_response=response.content
        usage_data=response.usage_metadata
        clean_json_str = raw_response.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(clean_json_str)
        token_calculator.add_usage(category='routing',input=usage_data['input_tokens'],output=usage_data['output_tokens'])
        print("TOKEN COUNT PROCESS:",usage_data['input_tokens'],"  ",usage_data['output_tokens'])
        return {"data":data}
    except Exception as e:
        print(str(e), 'exception from LLM routing function')
        return str(e)
    
async def handle_general_questions_llm4(user_query, llm_model):
    try:
        # Initialize Gemini model with specified parameters
        
        prompt = """# You are a customer support assistant who is expert in assiting for the topics of energy management systems,production management,quality management,utility management,wages management and electrical-related topics.
# You must strictly analyse the user question and check their question is under any of the topic and assist them with their queries.
# Provide friendly and helpful support, including troubleshooting and usage instructions, only related to the above topics i described above. 
# Please ignore any unrelated questions and gently remind the user to ask questions related to topics i described above. 
# Output should be in the HTML format no need for start with <html>; it should start with <div></div>. 
# Output should be within 500 tokens. Question: {user_query}. 
# Output should be in object format with 'description' and 'content' as key. 
# 'content' is in HTML format as mentioned, and 'description' is a very short summary. 
# Ensure the output is a raw JSON object without any code block formatting.
# Output should be strictly in object format without any formating or explanations. 
# Sample output format:{{ "description": "Short summary", "content": "<div>Your content here...</div>" }}
# strictly return the single object with all the values stored in the content as HTML format."""
        
        prompt_template = PromptTemplate(template=prompt, input_variables=['user_query'])
        model_execution = prompt_template | gemini_model
        response = await asyncio.to_thread(model_execution.invoke,{'user_query': user_query})
        raw_response = response.content
        usage_data = response.usage_metadata
        print(raw_response,"usage data")
        # token_calculator_object.add_usage(category='general_questions', input=usage_data['input_tokens'], output=usage_data['output_tokens'])
        # print("TOKEN COUNT PROCESS:", usage_data['input_tokens'], "  ", usage_data['output_tokens'])
        
        # Clean the response and parse JSON
        clean_json_str = raw_response.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(clean_json_str)
        
        # Return data in the format expected by the UI
        return {
            "data": {
                "description": data.get('description', ''),
                "content": data.get('content', ''),
                "llm_type": "General"
            }
        }
    except Exception as e:
        print(str(e), 'exception from LLM_4 general questions')
        return {"error": str(e)}


async def rephrase_user_query(user_query,model_load,conversation_history,company_id,token_calculator):
    try:
        retrieve_meters= await retrieve_meter_names(user_query,company_id)
        print(retrieve_meters,"retrieved meters")
        # extract_modified_messages=[message.content for message in conversation_history if isinstance(message, AIMessage)][-2:]
        extract_modified_messages=conversation_history
        print(extract_modified_messages,"user message extrcation")
        prompt = '''
                You are an assistant that preprocesses user questions before they are sent to a code-generation LLM.
                Your responsibilities:
                    1) **Rephrase the user query** into a clear, unambiguous, and formal version that is easy for another LLM to understand and convert into code or SQL.
                    2) **If** the user query includes **specific references to meter names** (e.g., "main incomer", "factory og"), and a list of exact meter names from the knowledge base is provided, then:
                    - Replace the fuzzy meter names in the query with the best-matching exact meter names from the list.
                    **However**, if the query is more general and does not clearly specify individual meter names (e.g., "show all incomers", "get usage of my meters"), then:
                    - Do NOT perform any replacement using the knowledge base — just rephrase the query clearly always do not include the additional text like for all meters.
                    3) If the user query is vague or a follow-up, use the last complete user query to reconstruct the full question.
                    4) If the input is a greeting (e.g., "hi", "hello"):
                        - Respond with a friendly greeting.
                        - Set intent to "greet".
                    5) If the input is off-topic or irrelevant to electrical meter data:
                        - Respond: "Your question seems off-topic. Please ask about meter-related information."
                        - Set intent to "irrelevant".
                    6) If the input is a general question that requires conversational AI response rather than code/SQL generation (e.g., "What is energy efficiency?", "How do electrical meters work?", "What are the benefits of monitoring power consumption?"):
                        - Set intent to "general".
                        - Rephrase the query clearly for the general LLM to handle.
                    7) If the input is a valid query that requires code/SQL generation:
                        - Set intent to "query".

                CONTEXTUAL UNDERSTANDING & FOLLOW-UP HANDLING:
                    1) Use both `user_query` and `conversation_history` to understand the full intent.
                    2) If the current `user_query` is incomplete, vague, or refers back to previous queries (e.g., mentions only a name, scope, or metric), combine it with the most recent complete query to form a full, clear question.
                    3) Your goal is to reconstruct the user's full intent by blending the context of the prior question with the new input, when needed.
                    4) Examples:
                    - Prior: "What is the total consumption for all departments over the last six months?"
                        Current: "provide month wise"
                        ➤ Inferred: "Provide the month-wise total energy consumption for all departments over the last six months."
                    5) Always output a complete, context-aware version of the question as `modified_question`.

                Always return the output in the following JSON format:
                {{
                "rephrased_query": "<your final query here>"
                "intent": "<greet | irrelevant | general | query>"
                }}

                ### Input:
                User Query: {user_query}
                Matched Meter Names (from knowledge base): {matched_meter_names}
                CONVERSATION HISTORY:{conversation_history}

                Now return the final rephrased query, with meter replacements applied only if appropriate.
                Do not explain your reasoning. Return ONLY the JSON.
        '''
        prompt_template = PromptTemplate(template=prompt, input_variables=['user_query','matched_meter_names','conversation_history'])
        model_execution = prompt_template | model_load
        response = await asyncio.to_thread(model_execution.invoke,{'user_query':user_query,'matched_meter_names':retrieve_meters,'conversation_history':extract_modified_messages})
        raw_response=response.content
        usage_data=response.usage_metadata
        clean_json_str = raw_response.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(clean_json_str)
        token_calculator.add_usage(category='rephrasing',input=usage_data['input_tokens'],output=usage_data['output_tokens'])
        print("TOKEN COUNT PROCESS:",usage_data['input_tokens'],"  ",usage_data['output_tokens'])
        print(data,"data")
        
        # Handle general questions immediately if intent is "general"
        if data.get('intent') == 'general':
            print("Handling general question with LLM_4")
            llm4_response = await handle_general_questions_llm4(user_query=data['rephrased_query'], llm_model=model_load)
            if 'error' in llm4_response:
                return {"error": llm4_response['error']}
            return {
                "response": llm4_response['data']['description'], 
                "llm_output": llm4_response['data']['content'],
                "llm_type": llm4_response['data']['llm_type'],
                "intent": "general"
            }
        
        return {"data":data}
    except Exception as e:
        print(str(e), 'exception from LLM error correction')
        return {"corrected_code": None, "error": str(e)}
    
async def echarts_property_generator(data):
    try:
        prompt="""
                You are a data visualization expert that generates optimal configuration for Apache ECharts in React (echarts-for-react).
                Your task is to analyze a single sample data row (as JSON) and infer the correct chart type and all required ECharts options to produce a clear, user-friendly visualization. Even though you receive only one row, assume the dataset contains many similar rows.

                Instructions:
                    1. Analyze the sample JSON row and infer the best ECharts chart type: bar, line, pie, scatter, etc.
                    2. Choose based on:
                        - Count/type of numeric fields
                        - Presence of time or category fields
                        - Whether fields should be compared side-by-side or over time
                    3. Select the most appropriate x-axis field (e.g., category, time).
                    4. Select one or more numeric fields as y-axis (or for pie series).
                    5. Return a dynamic ECharts config with:
                        - title: readable chart title
                        - xAxis & yAxis: field names (and optional axis labels)
                        - series: mapped fields with type, names, and options
                        - tooltip: 'axis' or 'item'
                        - legend: visibility and position
                        - labels: whether to show values
                        - theme: "light" (default)
                        - color: default palette
                        - dataZoom: true for time/dense xAxis
                    6. Use field names from the sample row — never hardcode.
                    7. Respond with JSON in the exact structure below (no explanation).

            Always return your response in this JSON structure (no explanation):
                
            {{"echart_properties:{{
                "chartType": "bar" | "line" | "pie" | "scatter",
                "title": "string",
                "xAxis": {{
                    "field": "string",
                    "name": "string (optional)"
                }},
                "yAxis": {{
                    "fields": ["string", "..."],
                    "names": ["string", "..."]
                }},
                "series": {{
                    "stacked": boolean,
                    "smooth": boolean,
                    "areaStyle": boolean
                }},
                "legend": {{
                    "show": boolean,
                    "position": "top" | "bottom" | "left" | "right"
                }},
                "tooltip": {{
                    "trigger": "axis" | "item"
                }},
                "labels": {{
                    "show": boolean
                }},
                "theme": "light" | "dark",
                "dataZoom": {{
                    "enabled": boolean
                }},
                "color": ["#5470C6", "#91CC75", "#FAC858"]
                }}
            }}

                refer to the input data here: {input_data}

                Output Format:
                Only return a valid JSON object as per the structure above.

            Now, generate the appropriate ECharts configuration based on the data.
        """
        prompt_template=PromptTemplate(template=prompt,input_variables=['input_data'])
        model_load=prompt_template|gemini_model
        response=model_load.invoke({"input_data":data})
        response=response.content
        clean_json_str = response.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(clean_json_str)
        return data
    except Exception as e:
        return str(e)

  
async def retrieve_AI_responses(user_query,chroma_db_client,llm_model,embedding_model,session_id,user_id,company_id,token_calculator):
    try:
        print(company_id,"company id")
        print("user_query",user_query)
        knowledge_context=None
        # history=memory.load_memory_variables({})['history']
        history= await get_conversation_history(user_id=user_id,session_id=session_id)
        history=[conversation['messages'] for conversation in history]
        rephrased_user_query=await rephrase_user_query(user_query=user_query,model_load=llm_model,conversation_history=history,company_id=company_id,token_calculator=token_calculator)
        print(rephrased_user_query,"rephrased user query")
        
        # Handle different response formats from rephrase_user_query
        if 'error' in rephrased_user_query:
            return {"error": rephrased_user_query['error']}
        
        # If it's a general question, return the response directly
        if rephrased_user_query.get('intent') == 'general':
            return {
                "response": rephrased_user_query['response'], 
                "llm_output": rephrased_user_query['llm_output'],
                "llm_type": rephrased_user_query['llm_type'],
                "intent": "general"
            }
        
        # Handle greet and irrelevant intents
        if rephrased_user_query['data']['intent']=="greet" or rephrased_user_query['data']['intent']=="irrelevant":
            return {"response":rephrased_user_query['data']['rephrased_query'],"intent":rephrased_user_query['data']['intent']}
        else:
            handle_routing_action=await handle_llm_routing_action(user_query=rephrased_user_query['data']['rephrased_query'],model=llm_model,token_calculator=token_calculator)
            print(handle_routing_action['data'],"action data")
            prompt='''
            TASK:
                Generate optimized Python code with an embedded MSSQL query to answer:
                "{user_query}"

                CONTEXT:
                {knowledge_data}

            METER NAME FILTERING CONDITION:
                If the user query clearly mentions one or more meter names (e.g., "Main Incomer 33kV", "TR5", "U22_SB_INCOMER"), then:
                    ➤ The SQL query MUST include this condition in the WHERE clause:
                        AND e.name LIKE '%<user meter name>%'
                    ➤ Use one `LIKE` clause per meter name, joined with `OR` if there are multiple.
                    ➤ This must be used in addition to the standard entity ID filtering.
                    ➤ Ensure that LIKE clauses are case-insensitive by using `e.name` if the column is not case-sensitive, or apply `LOWER()` if necessary.
    
            General Rules:
                1) Always generate complete, valid Python + MSSQL code with no empty outputs.
                2) Return only Python code inside a single JSON key: "code".
                3) Use only SELECT queries. Never generate INSERT/UPDATE/DELETE/DROP.
                4) Use only columns/tables found in {{knowledge_data}}.
                5)Always filter with:
                    e.company_id = :company_id
                    e.id IN (:entity_0, :entity_1, ...)
                    e.e_deleted = 0
                6)Always include all the defined import statements in code.
            DATE RANGE FILTERING CONDITIONS:
                When the user query mentions time periods, interpret them as complete periods:
                    ➤ "This month" = Current month start (1st) to current month end (last day)
                    ➤ "Last month" = Previous month start (1st) to previous month end (last day)
                    ➤ "This week" = Current week Monday to current week Sunday
                    ➤ "Last week" = Previous week Monday to previous week Sunday
                    ➤ "This year" = January 1st to December 31st of current year
                    ➤ "Last year" = January 1st to December 31st of previous year
            DATETIME PARAMETER FORMATTING RULE:
                ➤ When passing datetime objects as parameters to SQL queries, ALWAYS convert them to string format 'yyyy-MM-dd HH:mm' before adding to params dictionary.
                ➤ NEVER pass datetime.datetime objects directly to SQL parameters.
                ➤ Use .strftime('%Y-%m-%d %H:%M') method to convert datetime objects to the required string format.
            
            DATE PARAMETER CASTING & FORMATTING RULE:
                ➤ Always cast string date parameters before formatting: FORMAT(CAST(:date_param AS DATETIME), 'dd-MMM-yyyy') instead of FORMAT(:date_param, 'dd-MMM-yyyy')
                ➤ Apply this casting pattern for all date formats: 'dd-MMM-yyyy', 'dd-MMM-yyyy HH:mm', and 'MMM-yyyy'
            
            MSSQL Query Standards:
                1) Prefix tables with schema (e.g., masterdb.table)
                2) Use TOP 1000 unless user requests more/less
                3) Use ISNULL() for NULL values
                4) Format dates:
                    Date → dd-MMM-yyyy
                    Datetime → dd-MMM-yyyy HH:mm
                    Month → MMM-yyyy
                5) Use FORMAT() with CAST('YYYY-MM-DD' AS DATE)
                6) Use ROUND(..., 2) for numeric values
                7) Use text() + named parameters only (e.g., :company_id)
                8) Avoid assumptions about columns

            Rules for E-Charts generation:
                1. Analyze the sample JSON row and infer the best ECharts chart type: bar, line, pie, scatter, etc.
                2. Choose based on:
                    - Count/type of numeric fields
                    - Presence of time or category fields
                    - Whether fields should be compared side-by-side or over time
                3. Select the most appropriate x-axis field (e.g., category, time).
                4. Select one or more numeric fields as y-axis (or for pie series).
                5. Return a dynamic ECharts config with:
                    - title: readable chart title
                    - xAxis & yAxis: field names (and optional axis labels)
                    - series: mapped fields with type, names, and options
                    - tooltip: 'axis' or 'item'
                    - legend: visibility and position
                    - labels: Always set to True
                    - theme: "light" (default)
                    - color: default palette
                    - dataZoom: true for time/dense xAxis
                6. Use field names from the sample row — never hardcode.
                7. Respond with JSON in the exact structure below (no explanation).
                8. Only generate echart_properties if a meaningful chart can be produced from the sample data. If the data is unsuitable for visualization (e.g., only identifiers, no numeric/time fields), then do not generate anything for echart_properties.

            Always return your response in this JSON structure (no explanation):
                
            
            Sample E-Charts Structure:
               {{"echart_properties:{{
                "chartType": "bar" | "line" | "pie" | "scatter",
                "title": "string",
                "xAxis": {{
                    "field": "string",
                    "name": "string (optional)"
                }},
                "yAxis": {{
                    "fields": ["string", "..."],
                    "names": ["string", "..."]
                }},
                "series": {{
                    "stacked": boolean,
                    "smooth": boolean,
                    "areaStyle": boolean
                }},
                "legend": {{
                    "show": boolean,
                    "position": "top" | "bottom" | "left" | "right"
                }},
                "tooltip": {{
                    "trigger": "axis" | "item"
                }},
                "labels": {{
                    "show": boolean
                }},
                "theme": "light" | "dark",
                "dataZoom": {{
                    "enabled": boolean
                }},
                "color": ["#5470C6", "#91CC75", "#FAC858"]
                }}
            }}

            CRITICAL SQL RULE: 
                1) Use CTEs only when necessary for modular or multi-step logic; avoid using them for single-row values, don't use `JOIN ON 1=1`, avoid `ORDER BY` or `TOP` inside CTEs, and always use valid join conditions.
            Python Code Structure to follow:
            {{
                from sqlalchemy import text
                import datetime
                from decimal import Decimal

                async def execute_query(query, params=None):
                    try:
                        async with engine.connect() as connection:
                            result = await connection.execute(query, params or {{}})
                            results = [dict(row._mapping) for row in result]
                            return {{"data":result,"description":<natural, non-technical summary, max 3–4 lines>,
                            "session_name":<user-friendly one-line heading upto 3 words max>,"insights":<actionable suggestions or helpful tips related to the query>,'modified_question':<modified user query with same context if follow up question asked based on conversation history.>,
                            "echart_properties": <generated ECharts config based on sample_row when consists of Numeric data type else return as 'None'>}}
                    except Exception as e:
                        return {{"error": str(e)}}
                    finally:
                        await connection.close()

                async def run(company_id=40, entity_id=(0, 1)):
                    try:
                        placeholders = ','.join(f':entity_{{i}}' for i in range(len(entity_id)))
                        query = text(f"""
                        -- YOUR GENERATED MSSQL SELECT QUERY GOES HERE
                        -- FOR HISTORICAL: Replace with entity fetching + device loop pattern
                        """)
                        params = {{'company_id': company_id}}
                        for i, eid in enumerate(entity_id):
                            try:
                                params[f'entity_{{i}}'] = eid
                            except:
                                continue
                        result = await execute_query(query, params)
                        return result
                    except Exception as e:
                        return {{"error": str(e)}}
            }}

            Output Format:
                {{"code": "<entire code block as string>"}}

            Response Formatting Rules:
                1) All keys inside data key should be in PascalCase (Meter Name, Start Date, Average kWh etc.)
                2) Output should always be a flat array of JSON objects (no nesting).
                3) Exclude technical IDs unless explicitly asked (e.g., “include meter ID”).

            Additional Tips:
                1) Use text(f""" ... """) for multi-line SQL.
                2) Use :param and a Python dict for query parameters.
                3) Do not hallucinate schema or column names.
                4) Avoid inline comments. Only return code.
                5) Don't modify function names or structure.

            
            STRICT ENFORCEMENT:
                1) Always include the exact line: `results = [dict(row._mapping) for row in result]` in the `execute_query` function.
                2) Never replace this line with custom row parsing. Do not skip, modify, or restructure this logic.

            Content Rules for Description, Session Name, and Insights:
                1) **description**: Think of this like you're talking to a colleague or friend — explain what the data shows in a clear, simple way. Keep it short (3–4 lines), stay casual, and avoid technical terms. Just help the user understand what they’re looking at and why it might be useful.
                2) **session_name**: Give it a short, clear title.
                3) **insights**: Offer a helpful thought or tip based on the result. Maybe point out a pattern, suggest what the user could explore next, or highlight something they might not notice right away. Keep it friendly and useful — like advice you’d give during a quick team chat.
    '''
            # get_kb_data=retrieve_KB_response(user_query=user_query,client=chroma_db_client,text_embedding_model=embedding_model)
            prompt_template=PromptTemplate(template=prompt,input_variables=['user_query','knowledge_data'])
            model_execution=prompt_template|llm_model
            if handle_routing_action['data']['routing_decision']=='LLM_1':
                knowledge_context=get_kb_data['get_consumption_kb_data']
            elif handle_routing_action['data']['routing_decision']=='LLM_2':
                knowledge_context=get_kb_data['get_historical_kb_data']
            elif handle_routing_action['data']['routing_decision']=='LLM_3':
                knowledge_context=get_kb_data['get_alarm_data']
            else:
                knowledge_context=[get_kb_data[x] for x in list(get_kb_data.keys())[:2]]


            response = await asyncio.to_thread(model_execution.invoke,{
                'user_query':rephrased_user_query['data']['rephrased_query'],'knowledge_data':knowledge_context
            })
            usage_data=response.usage_metadata
            token_calculator.add_usage(category='main_response',input=usage_data['input_tokens'],output=usage_data['output_tokens'])
            formatted_response= await extract_python_code(response.content)
            # print(response,'all responses printingk')
            # json_loaded=json.loads(response.content)
            # formatted_response=json_loaded['code']
            print(formatted_response,"generated code")
            print("TOKEN COUNT PROCESS:",usage_data['input_tokens'],"  ",usage_data['output_tokens'])
            return {"formatted_response":formatted_response,'llm_type':handle_routing_action['data']['routing_decision']}
    except Exception as e:
        print(str(e),'exception from LLM response')
        return str(e)



async def resolve_code_error_with_llm(generated_code, error_message, user_query, llm_model, token_calculator, knowledge_data=None,routing=None):
    try:
        print("came inside the second LLM")
        print(error_message,"error message in second LLM")
        knowledge_context=None
        prompt = '''
        Your task is to correct the following Python code (which includes an embedded MSSQL query) that was generated in response to a user's query but failed during execution.
            USER QUERY:
            {user_query}

            GENERATED CODE:
            {generated_code}

            ERROR MESSAGE:
            {error_message}


            INSTRUCTIONS:
                1) Analyze the provided code, error message, and user query.
                2) Correct the code to ensure successful execution while preserving the structure.
                3) Only return the corrected code in the following strict JSON format (as a string):
                   {{"code": "<corrected code as string>"}}
                4) Do not include explanations, comments, or any text other than the required JSON object.
                5) Do not change the existing code structure unnecessarily. Fix only what's required to resolve the issue.
        '''

        
        # if routing=="LLM_1":
        #     knowledge_context=get_kb_data['get_consumption_kb_data']
        # elif routing=="LLM_2":
        #     knowledge_context=get_kb_data['get_historical_kb_data']
        # elif routing=="LLM_3":
        #     knowledge_context=get_kb_data['get_alarm_data']
        # else:
        #     knowledge_context=[get_kb_data[x] for x in list(get_kb_data.keys())[:2]]
        prompt_template = PromptTemplate(template=prompt, input_variables=['user_query','generated_code','error_message'])
        model_execution = prompt_template | llm_model
        response =await asyncio.to_thread(model_execution.invoke,{'user_query':user_query,'generated_code':generated_code,'error_message':error_message})
        usage_data = response.usage_metadata
        token_calculator.add_usage(category='error_correction',input=usage_data['input_tokens'],output=usage_data['output_tokens'])
        print("TOKEN COUNT PROCESS:",usage_data['input_tokens'],"  ",usage_data['output_tokens'])
        corrected_code = await extract_python_code(response.content)
        print("corrected code",corrected_code)
        return {"corrected_code": corrected_code}
    except Exception as e:
        print(str(e), 'exception from LLM error correction')
        return {"corrected_code": None, "error": str(e)}
    
async def retrieve_image_context(user_query, base64_string,llm_model,token_calculator):
    try:        
        system_prompt="""
Look at the provided image and act like a friendly data assistant inside the app. 
Understand the context, read any visible data, find trends or anomalies, and talk casually to the user with useful insights, not just repeating what’s visible.

Your output must:
- Start with a short friendly greeting.
- Give key takeaways from the data (trends, risks, wins, anomalies).
- Add a few actionable tips or recommendations.
- Keep it interactive in tone: use phrases like "I noticed", "You might want to", "Looks like".
- Avoid describing the layout — focus on meaning and implications.


Output format:
Return only JSON: {{"data": "<HTML here>"}}.
HTML must:
- Include a <style> block with a modern professional theme:
    - Use Professional Heading color.
    - Highlight key numbers with appropriate color for better interaction.
    - Bullet lists styled with colorful markers like arrow.
    - Slight hover effect on list items for interactivity feel.
    - Always generate the important points, heading in bolder color.
- Organize into: Greeting with small explanation about page, Insights, Recommendations.
- Keep it under 1000 tokens.
"""
        system_message=SystemMessage(content=system_prompt)
        message = HumanMessage(
            content=[
                {"type": "text", "text": user_query},
                {"type": "image_url", "image_url": {"url": base64_string}}
            ]
        )
        response =await asyncio.to_thread(llm_model.invoke,[system_message,message])
        usage_data = response.usage_metadata
        print(usage_data,"usage tokensss")
        # print("TOKEN COUNT:", response.usage_metadata)
        response=response.content
        # token_calculator.add_usage(category='error_correction',input=usage_data['input_tokens'],output=usage_data['output_tokens'])
        clean_json_str = response.strip().removeprefix("```json").removesuffix("```").strip()
        print(clean_json_str,"cleaned text")
        data = json.loads(clean_json_str)
        print("Data",data['data'])
        return data['data']
    except Exception as e:
        print("Error:", str(e))
        return None












    





