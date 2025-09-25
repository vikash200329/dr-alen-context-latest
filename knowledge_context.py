get_kb_data={
  "get_consumption_kb_data": {
  "context": "Energy Management Database Context\n\n## Tables & Hierarchy\n- **masterdb.entities**: id, name, level_id, company_id, e_deleted\n  - Levels: 1=meter, 2=department, 3=dept_group, 4=multi_dept_group\n- **masterdb.rollup1_entities**: entity_id, metric_rollup1 (kWh), metric_rollup2 (kVAh), metric_rollup3 (Export kWh), rollup_date, reference_period_id, reference_period_item_id\n  - Periods: 4=shift, 5=day\n  - NO company_id column - must JOIN with entities\n- **masterdb.entity_masters**: parent_entity_id, child_entity_id (for hierarchy)\n- **masterdb.reference_period_items**: id, reference_point, company_id (dynamic shifts per company)\n- **masterdb.entity_targets**: id, entity_id, reference_period_id, target_date, target_type_id, target_value, e_deleted\n  - Daily targets only (reference_period_id = 5)\n  - Only target_type_id = 1 used — no need to join target_types\n  - Must JOIN `entities` for company_id and access control\n  - Use when user asks for target values or compares actual vs. target\n\n## Critical Security Rules\n- **MANDATORY**: Always include these 4 security filters:\n  - `e.company_id = :company_id` (company isolation)\n  - `e.e_deleted = 0` (exclude soft-deleted records)\n  - `e.id IN (:entity_ids)` (user access control)\n  - `e.level_id = :level_id` (entity level filter - prevents double counting)\n- **Standard JOIN**: `JOIN entities e ON r.entity_id = e.id WHERE e.company_id = :company_id AND e.e_deleted = 0 AND e.id IN (:entity_ids) AND e.level_id = :level_id`\n- **Shifts**: NEVER hardcode shift names - query `reference_period_items WHERE company_id = :company_id ORDER BY id`\n- **Hierarchy**: Use `entity_masters` for parent-child relationships\n- **Data Source**: Consumption data from `rollup1_entities`, target data from `entity_targets`\n\n## Level Selection Rules\n- **ALWAYS add level_id filter** to prevent double counting across hierarchy levels\n- **Default level_id = 1** (meters) for all general/overall questions\n- **Only change level_id when user specifically asks about:**\n  - Departments: level_id = 2\n  - Department groups: level_id = 3\n  - Multi-department groups: level_id = 4\n- **Exception**: Skip level_id filter ONLY when user mentions specific entity names AND you need to search across all levels to find the named entity\n\n## Period Selection Rules\n- **Shift Analysis**: Only when user specifically asks about shifts/shift-wise data\n  - Use `reference_period_id = 4`\n  - Must JOIN `reference_period_items` table\n  - Filter by `reference_period_item_id IN ({shift_ids})`\n- **Day Analysis**: Default for all other queries (daily, weekly, monthly, weekdays, weekends)\n  - Use `reference_period_id = 5`\n  - DO NOT join `reference_period_items` table\n  - NO reference_period_item_id filter needed\n\n## Aggregation Handling\n- **Group only by requested dimensions**: Group only by fields explicitly mentioned in the question (e.g., date, meter, department). If user asks for totals by date only (like day-wise), exclude meter from `GROUP BY` and `SELECT`.\n- **Avoid extra grouping**: Avoid adding extra dimensions in `GROUP BY` or `SELECT` unless explicitly required; ensures correct totals without over-segmentation.\n\n## Validation Checklist\n- [ ] Company filter included (`e.company_id = :company_id`)?\n- [ ] Soft-deleted records excluded (`e.e_deleted = 0`)?\n- [ ] User access control applied (`e.id IN (:entity_ids)`)?\n- [ ] Level filter applied (`e.level_id = :level_id`) to prevent double counting?\n- [ ] Consumption from rollup1_entities table?\n- [ ] Correct period selection (shift=4 vs day=5)?\n- [ ] reference_period_items table only joined for shifts?\n- [ ] Shifts queried dynamically (no hardcoded names)?\n- [ ] Hierarchy via entity_masters for parent-child queries?\n- [ ] Grouping only on requested dimensions?\n- [ ] Target data from entity_targets when targets mentioned?\n- [ ] No unnecessary ORDER BY in CTEs or subqueries (only in final SELECT or window functions)?\n\n## Query Requirements\n- Use `masterdb.` schema prefix\n- MSSQL syntax: TOP, DATEADD, DATEPART, ISNULL()\n- Date format: 'YYYY-MM-DD', cast strings: `CAST('2025-06-01' AS DATE)`\n\n## Response Format\n- Business names: \"Meter Name\", \"Department Name\"\n- Dates: dd-MMM-yyyy, Numbers: ROUND(,2)\n- Units: include kWh/kVAh in results\n- Exclude IDs unless requested",
  "schema": "masterdb",
  "tables": [
    {
      "name": "entities",
      "type": "master",
      "columns": ["id:int:pk", "name:varchar", "level_id:int", "company_id:int", "e_deleted:bit"],
      "constraints": ["e_deleted=0", "company_id=:company_id", "id IN (:entity_ids)", "level_id=:level_id"],
      "levels": [[1, "meter"], [2, "dept"], [3, "dept_group"], [4, "multi_dept_group"]],
      "default_level": 1,"Do not apply when user specifically defined the entity name in user query."
      "level_filter_rule": "Always required to prevent double counting across hierarchy levels ignore if user question consists of entity name"
    },
    {
      "name": "rollup1_entities",
      "type": "fact",
      "columns": ["entity_id:int:fk", "metric_rollup1:decimal:kWh", "metric_rollup2:decimal:kVAh", "metric_rollup3:decimal:export kWh", "rollup_date:date", "reference_period_id:int", "reference_period_item_id:int:fk"],
      "joins": ["entities:entity_id=id"],
      "periods": [[4, "shift"], [5, "day"]],
      "alert": "missing company_id - must JOIN with entities"
    },
    {
      "name": "entity_masters",
      "type": "bridge",
      "columns": ["parent_entity_id:int:fk", "child_entity_id:int:fk"],
      "direction": "parent->child"
    },
    {
      "name": "reference_period_items",
      "type": "lookup",
      "columns": ["id:int:pk", "reference_point:varchar", "company_id:int"],
      "dynamic": "SELECT id,reference_point FROM masterdb.reference_period_items WHERE company_id=:company_id ORDER BY id",
      "note": "shift names vary by company - never hardcode",
      "usage": "Only join when reference_period_id=4 (shifts) OR when user specifically asks for shift details/information"
    },
    {
      "name": "entity_targets",
      "type": "fact",
      "columns": ["id:int:pk", "entity_id:int:fk", "reference_period_id:int", "target_date:datetime", "target_type_id:int", "e_deleted:int", "hierarchy_id:int", "target_value:float", "reference_period_item_id:int"],
      "joins": ["entities:entity_id=id"],
      "constraints": ["e_deleted=0", "entity_id IN (:entity_ids)", "target_type_id IN (1)", "reference_period_id = 5"],
      "note": "Stores daily energy targets at entity level. Must join entities to apply company_id."
    }
  ],
  "relationships": [
    ["entities", "rollup1_entities", "id=entity_id"],
    ["entities", "entity_masters", "id=parent_entity_id|child_entity_id"],
    ["reference_period_items", "rollup1_entities", "id=reference_period_item_id (only for shifts)"],
    ["entities", "entity_targets", "id=entity_id"]

  ],
  "templates": {
    "base": "SELECT {fields} FROM rollup1_entities r JOIN entities e ON r.entity_id=e.id WHERE e.company_id=:company_id AND e.e_deleted=0 AND e.id IN (:entity_ids) AND e.level_id=:level_id",
    "shift": "AND r.reference_period_id=4 AND r.reference_period_item_id IN ({shift_ids})",
    "Shift Details":"select reference_point from masterdb.reference_period_items where company_id = :company_id order by id",
    "daily": "AND r.reference_period_id=5",
    "date_range": "AND r.rollup_date BETWEEN :start_date AND :end_date",
    "shift_with_join": "JOIN reference_period_items rpi ON r.reference_period_item_id=rpi.id AND rpi.company_id=:company_id",
    "target_base": "SELECT {fields} FROM masterdb.entity_targets t JOIN masterdb.entities e ON t.entity_id = e.id WHERE e.company_id = :company_id AND e.e_deleted = 0 AND t.e_deleted = 0 AND e.id IN (:entity_ids) AND e.level_id = :level_id AND t.reference_period_id = 5 AND t.target_type_id IN (1)"

  },
  "rules": [
    "always_filter_company_id",
    "always_filter_deleted",
    "always_filter_entity_ids",
    "always_filter_level_id",
    "default_level_id_is_1",
    "level_id_prevents_double_counting",
    "shift_only_when_requested",
    "day_analysis_for_all_other_queries",
    "reference_period_items_only_for_shifts",
    "dynamic_shift_lookup",
    "join_for_company_filter",
    "group_only_by_requested_dimensions",
    "avoid_unnecessary_grouping_for_total_aggregation",
    "do_not_apply_level_id_when_entity_names_are_mentioned",
    "target_data_fixed_reference_period_and_type"   
  ],
  "notes": {
    "group_only_by_requested_dimensions": "Group only by fields explicitly mentioned in the question (e.g., date, meter, department). If user asks for totals by date only (like day-wise), exclude meter from GROUP BY and SELECT.",
    "target_data_fixed_reference_period_and_type": "Target queries always use reference_period_id = 5 (day) and target_type_id = 1. No need to join target_types or handle shifts.",
    "avoid_unnecessary_grouping_for_total_aggregation": "Avoid adding extra dimensions in GROUP BY or SELECT unless explicitly required; ensures correct totals without over-segmentation."
  }
},
"get_historical_kb_data": {
  "context": """
Electrical Meter Database Context
Tables & Structure
* **masterdb.entities**: id, name, level_id, device_id, company_id, e_deleted (master table)
* **masterdb.tblmeters**: meterid, DESCRIPTION, MODEL, DATAINTERVAL, ig_sno, SITENAME, metername + config fields (meter configuration), consider 'ig_chn' as port 
* **masterdb.ig_informations**: serial_no, ig_name (IG master data)
* **masterdb.tblrtimemeterid**: METERID, TDATETIME, validrec + electrical parameters (real-time data)
* **masterdb.tbllogsmeterid{device_id}**: TDATETIME, validrec + electrical parameters (historical data per device)

Security Filters (MANDATORY - Always Include)

```sql
WHERE e.company_id = :company_id 
  AND e.e_deleted = 0 
  AND e.id IN (:entity_ids) 
  AND rt.validrec = 1  -- Skip for non-communicating queries
```

Query Selection Rules
* **Real-time Data**: Use `tblrtimemeterid` when user asks for "current", "now", "latest", "live", or communication status or **No specific date/time period mentioned** in question (DEFAULT to real-time)
   * Join: `JOIN entities e ON rt.METERID = e.device_id`
* **Historical Data**: Use `tbllogsmeterid{device_id}` for date ranges, trends, specific periods or relative terms like 'today', 'yesterday', 'last week', etc. These queries must be executed using a try-catch loop across dynamic tables.
   * No METERID column - use device_id as table suffix
   * CROSS APPLY and OUTER APPLY must NEVER be used. These will fail for dynamic historical tables like `tbllogsmeterid{device_id}` where the outer reference (`device_id`) is not resolvable.
   * Always include date range filters
* **Meter Configuration**: Use `tblmeters` for meter details, models, data intervals, IG connections
   * Join: `JOIN tblmeters tm ON e.device_id = tm.meterid`
* **IG Information**: Use `ig_informations` for IG details and meter-IG relationships
   * Join: `JOIN ig_informations ig ON tm.ig_sno = ig.serial_no`

Anomaly/Spike Detection Rules
* **Spike/Abnormality/Anomaly Detection**: When user asks for spikes, abnormalities, anomalies, unusual readings
* **Threshold Logic**: Reading is anomaly if `current_value > (10 * average_value)` 
* **Process**: Calculate average for parameter → Compare each reading → Flag values ≥10x average
* **Query Pattern**: Use CTE to calculate average, then filter/flag anomalous readings
* **Parameters**: Apply to electrical params like VL, IL, KWT, KVAT, etc. based on user query
* **Energy Anomaly**: For energy-related anomaly detection, always use KWHDEL parameter
* **Zero Value Filter**: Always include `parameter > 0` condition to avoid conflicts with zero readings

Data Quality Monitoring
* **Data Interval**: `tm.DATAINTERVAL` defines expected reading frequency (minutes: 5, 15, 30, etc.)
* **Target Rows**: Calculate expected records = `(date_range_minutes / DATAINTERVAL)`
* **Actual vs Target**: Compare actual row count with target for data percentage
* **IG-Meter Mapping**: Count meters per IG using `GROUP BY ig.ig_name, ig.serial_no`

Historical Query Strategy (CRITICAL)
**Problem**: Cannot use dynamic table names in SQL **Solution**: Execute separate queries for each device in Python loop

```python
# Step 1: Get valid entities
entity_query = text(\"\"\"
SELECT e.name AS [Meter Name], e.device_id
FROM masterdb.entities e
WHERE e.company_id = :company_id AND e.e_deleted = 0 
  AND e.id IN (:entity_ids) AND e.device_id IS NOT NULL 
  AND e.device_id > 0 AND e.level_id = 1
\"\"\")

with engine.connect() as connection:
    entity_result = connection.execute(entity_query, params)
    entities = [dict(row._mapping) for row in entity_result]

# Step 2: Loop through each device with try-catch for missing columns
all_results = []
for entity in entities:
    try:
        meter_name=entity.get('Meter Name','')
        device_id=entity.get('device_id',0)
        device_query = text(f\"\"\"
        SELECT '{entity['Meter Name']}' AS [Meter Name], {aggregated_fields}
        FROM masterdb.tbllogsmeterid{device_id} hl
        WHERE hl.TDATETIME BETWEEN :start_date AND :end_date AND hl.validrec = 1
        \"\"\")
        result = execute_query(device_query, params)
        return result
    except Exception:
        # Skip meter if columns missing, continue with others
        continue
```

Electrical Parameter Selection Rules
* **Voltage**: Default=VL | Individual phases="VL1,VL2,VL3" | Line-to-line="VRY,VYB,VBR" | 3-phase avg=VRYB
* **Current**: Default=IL | Individual phases="IR,IY,IB" | Neutral=NC
* **Power**: Active=KWT | Apparent=KVAT | Reactive=KVART | Phase active="KWR,KWY,KWB"
* **Energy**: Delivered=KWHDEL | Received=KWHREC | Reactive="KVARHDEL,KVARHREC" | Apparent=KVAH
* **Demand**: Active=KWD | Apparent=KVAD | **Peak Demand=KVAPD** | Peak reactive=KVARPD
* **Power Factor**: Default=PFL | Individual phases="PFR,PFY,PFB"
* **Frequency**: HZ | **Runtime**: RunHours

Parameter Priority Logic:
- Use DEFAULT unless user specifies "phases", "individual", "each phase", "line-to-line"
- "All phases" voltage → VL1,VL2,VL3 | "Phase voltage" → VRY,VYB,VBR
- "Total" or unspecified → use default single parameter

**⚠️ MISSING COLUMN HANDLING**: 
- Not all electrical parameters exist in all meter tables - use try-catch in device loops
- Continue processing other meters even if one fails due to missing columns

Communication Status
* **Communicating/online**: `validrec=1 AND TDATETIME >= DATEADD(minute,-30,GETDATE())`
* **Non-communicating/offline**: `validrec=0`

Important Rules
* Use `masterdb.` schema prefix always
* MSSQL syntax: TOP, DATEADD, DATEPART, ISNULL()
* Date format: 'YYYY-MM-DD HH:mm:ss'
* Round decimals: `ROUND(,2)` for values, `ROUND(,3)` for power factor
* Device ID validation: `AND e.device_id IS NOT NULL AND e.device_id > 0`
* Any temporal indicator, including “today”, “yesterday”, “last week”, etc., classify it under "historical"
* **Column validation**: Use try-catch in device loops for missing columns
* **Data Quality**: Use DATAINTERVAL to calculate expected vs actual row counts
* **Anomaly Detection**: Use 10x average threshold for spike detection
* **No Comments**: Never add comments in generated code
* ❌ NEVER use: dynamic SQL, UNION ALL for historical, temp tables, DDL/DML operations
* ❌ NEVER use: **CROSS APPLY** with dynamic table names
* ❌ NEVER assume all columns exist in all meter tables - use try-catch
""",
  "schema": "masterdb",
    "electrical_params": "TDATETIME:datetime,validrec:int,VL:decimal,IL:decimal,KWT:decimal,KVAT:decimal,KVART:decimal,PFL:decimal,HZ:decimal,KWHDEL:decimal,KVAH:decimal,KWHREC:decimal,KVARHDEL:decimal,KVARHREC:decimal,KVAD:decimal,KVAPD:decimal,KWD:decimal,KVARPD:decimal,VL1:decimal,VL2:decimal,VL3:decimal,IR:decimal,IY:decimal,IB:decimal,KWR:decimal,KWY:decimal,KWB:decimal,PFR:decimal,PFY:decimal,PFB:decimal,VRTHD:decimal,VYTHD:decimal,VBTHD:decimal,IRTHD:decimal,IYTHD:decimal,IBTHD:decimal,NC:decimal,VRY:decimal,VYB:decimal,VBR:decimal,VRYB:decimal,KVAR:decimal,KVAY:decimal,KVAB:decimal,KVARR:decimal,KVARY:decimal,KVARB:decimal,RunHours:decimal",
    "tables": [
        {
            "name": "entities",
            "type": "master",
            "columns": ["id:int:pk", "name:varchar", "level_id:int", "device_id:bigint", "company_id:int", "e_deleted:bit"],
            "constraints": ["e_deleted=0", "company_id=:company_id", "id IN (:entity_ids)"],
            "levels": [[1,"meter"],[2,"department"],[3,"department_group"],[4,"multi_department_group"]]
        },
        {
            "name": "tblmeters",
            "type": "config",
            "columns": ["meterid:varchar:fk", "DESCRIPTION:varchar", "MODEL:varchar", "DATAINTERVAL:int", "device_modbusid:int", "channelno:int", "SITENAME:varchar", "ig_sno:varchar:fk", "ipaddress:varchar", "device_ip:varchar", "physical_index:int", "ig_chn:varchar", "metername:varchar"],
            "joins": ["entities:device_id=meterid", "ig_informations:ig_sno=serial_no"],
            "purpose": "meter configuration, data intervals, IG connections"
        },
        {
            "name": "ig_informations",
            "type": "config",
            "columns": ["serial_no:varchar:pk", "ig_name:varchar"],
            "joins": ["tblmeters:serial_no=ig_sno"],
            "purpose": "Intelligent Gateway master data"
        },
        {
            "name": "entity_masters",
            "type": "bridge",
            "columns": [
                "parent_entity_id:int:fk",
                "child_entity_id:int:fk"
            ],
            "direction": "parent->child",
            "note": "defines parent-child hierarchy"
        },
        {
            "name": "tblrtimemeterid",
            "type": "fact",
            "columns": ["METERID:bigint:fk", "...electrical_params"],
            "joins": ["entities:METERID=device_id"],
            "purpose": "real-time meter data",
            "communication_status": {
                "non_communicating": "validrec=0",
                "communicating": "validrec=1 AND TDATETIME >= DATEADD(minute, -30, GETDATE())"
            }
        },
        {
            "name": "tbllogsmeterid{device_id}",
            "type": "fact",
            "dynamic_table": True,
            "columns": ["...electrical_params"],
            "joins": ["entities:device_id=table_suffix"],
            "purpose": "historical meter data",
            "note": "separate table per device, no METERID column"
        }
    ],
    "relationships": [
        ["entities", "tblmeters", "device_id=meterid"],
        ["tblmeters", "ig_informations", "ig_sno=serial_no"],
        ["entities", "entity_masters", "id=parent_entity_id|child_entity_id"],
        ["entities", "tblrtimemeterid", "device_id=METERID"],
        ["entities", "tbllogsmeterid{device_id}", "device_id=table_suffix"]
    ],
	"mandatory_columns": {
        "communication_status": {
            "required": ["e.name AS [Meter Name]", "format(rt.TDATETIME,'dd-MMM-yyyy HH:mm') AS [Last Update]"],
            "description": "For online/offline, communicating/non-communicating queries"
        },
        "data_quality": {
            "required": ["e.name AS [Meter Name]","timestamp_field", "tm.DATAINTERVAL", "Actual rows", "Target Rows", "ROUND(((CAST(actual_rows AS FLOAT) / target_rows) * 100), 2) AS percentage"],
            "description": "For data percentage and quality queries, Always use tbllogsmeterid{device_id} dynamic tables"
        },
        "electrical_parameters": {
            "required": ["e.name AS [Meter Name]", "timestamp_field"],
            "timestamp_field": "rt.TDATETIME for real-time OR date grouping for historical (default datetime format: 'dd-MMM-yyyy HH:mm')",
            "description": "For energy, demand, power, voltage, current queries"
        },
        "configuration": {
            "required": ["e.name AS [Meter Name]", "tm.MODEL", "tm.DATAINTERVAL"],
            "description": "For meter configuration and setup queries"
        },
        "general_rule": "Every query MUST include meter identification (e.name AS [Meter Name]) + appropriate timestamp/date context + query-specific mandatory fields + user-requested additional fields"
    },
    "templates": {
        "real_time_base": "SELECT {fields} FROM masterdb.tblrtimemeterid rt JOIN masterdb.entities e ON rt.METERID = e.device_id WHERE e.company_id = :company_id AND e.e_deleted = 0 AND e.id IN (:entity_ids)",
        "meter_config": "SELECT {fields} FROM masterdb.entities e JOIN masterdb.tblmeters tm ON e.device_id = tm.meterid LEFT JOIN masterdb.ig_informations ig ON tm.ig_sno = ig.serial_no WHERE e.company_id = :company_id AND e.e_deleted = 0 AND e.id IN (:entity_ids)",
        "ig_meter_count": "SELECT ig.ig_name, ig.serial_no, COUNT(tm.meterid) as meter_count FROM masterdb.ig_informations ig LEFT JOIN masterdb.tblmeters tm ON ig.serial_no = tm.ig_sno GROUP BY ig.ig_name, ig.serial_no",
        "data_quality_check": "SELECT COUNT(*) as actual_rows, cast(DATEDIFF(minute, :start_date, :end_date)+1 as float) / tm.DATAINTERVAL as target_rows FROM masterdb.tbllogsmeterid{device_id} hl, masterdb.tblmeters tm WHERE tm.meterid = :device_id AND hl.TDATETIME BETWEEN :start_date AND :end_date AND hl.validrec = 1 group by tm.DATAINTERVAL",
        "data_quality_daywise": "SELECT FORMAT(hl.TDATETIME, 'dd-MMM-yyyy') AS [Date], :meter_name AS [Meter Name], COUNT(*) AS [Actual Rows], CAST(1440.0 / tm.DATAINTERVAL AS FLOAT) AS [Target Rows] FROM masterdb.tbllogsmeterid{device_id} hl , masterdb.tblmeters tm WHERE tm.meterid = :device_id AND hl.TDATETIME BETWEEN :start_date AND :end_date AND hl.validrec = 1 GROUP BY FORMAT(hl.TDATETIME, 'dd-MMM-yyyy'), tm.DATAINTERVAL",
        "historical_direct": "SELECT {fields} FROM masterdb.tbllogsmeterid{device_id} hl",
        "current_data": "AND rt.validrec = 1",
        "valid_data": "AND validrec = 1",
        "date_range": "AND TDATETIME BETWEEN :start_date AND :end_date",
        "communication_check_communicating": "AND (rt.validrec = 1 AND rt.TDATETIME >= DATEADD(minute, -30, GETDATE()))",
        "communication_check_non_communicating": "AND rt.validrec = 0"
    },
    "rules": [
        "always_filter_company_id",
        "always_filter_deleted",
        "always_filter_entity_access",
        "use_real_time_for_current_latest_now",
        "use_historical_for_date_ranges_trends",
        "use_tblmeters_for_config_ig_mapping_data_intervals",
        "calculate_data_quality_using_datainterval",
        "include_validrec_1_for_valid_data_except_non_communicating",
        "round_values_2_decimals_3_for_pf",
        "format_dates_dd_MMM_yyyy_HH_mm_ss",
        "dynamic_historical_table_naming",
        "check_communication_status_30_minutes_for_communicating_only",
        "wrap_all_historical_queries_in_try_catch",
        "use_10x_average_threshold_for_anomaly_detection",
    ],
    "query_patterns": {
        "current": "real-time queries for 'current', 'now', 'latest', or communication status or No specific date/time period mentioned ",
        "historical": "historical queries for specific dates, periods, or trends",
        "configuration": "meter details, models, data intervals, IG connections",
        "data_quality": "actual vs target row counts using DATAINTERVAL",
        "ig_mapping": "IG-meter relationships and counts per IG",
        "anomaly_detection": "spikes, abnormalities, anomalies, unusual readings"
    }
},
"get_alarm_data": {
  "context": """
Alarm System Context
Tables: entities, alarm_settings, alarm_data

Security Filters (MANDATORY):
WHERE e.company_id = :company_id AND e.e_deleted = 0 AND e.id IN (:entity_ids)
Key Rules:
* Active Alarms: alarm_status = 0
* Alarm History: Use alarm_datetime date ranges  
* alarm_type: 0=High, 1=Low
* Duration format: 'HH:MM:SS' string
* Standard joins: alarm_data -> alarm_settings -> entities

Parameter Categories:
* Voltage: 16,18,19,20,21
* Current: 3,22,24  
* Power Factor: 4,25
* Power: 5(KW), 7(KVA)
* Demand: 37,38
* Communication: 870

Common Patterns:
- Active: ad.alarm_status = 0
- History: ad.alarm_datetime BETWEEN :start_date AND :end_date
- Parameter filter: aset.param_id IN (:param_ids)
- Base join: FROM alarm_data ad JOIN alarm_settings aset ON ad.alarm_id = aset.id JOIN entities e ON aset.device_id = e.device_id
""",
  "schema": "masterdb",
  "alarm_params": "alarm_id:int,alarm_datetime:datetime,alarm_trigger_value:decimal,alarm_value:decimal,percentage_crossed:decimal,alarm_status:int,alarm_duration:varchar",
  "tables": [
    {"name": "entities", "columns": ["id:int:pk", "name:varchar", "device_id:bigint", "company_id:int", "e_deleted:bit"]},
    {"name": "alarm_settings", "columns": ["id:int:pk", "device_id:bigint:fk", "alarm_name:varchar", "alarm_type:int", "param_id:int", "alarm_trigger_value:decimal", "alarm_release_value:decimal"]},
    {"name": "alarm_data", "columns": ["alarm_id:int:fk", "alarm_datetime:datetime", "alarm_value:decimal", "alarm_status:int", "alarm_duration:varchar", "percentage_crossed:decimal"]}
  ],
  "param_ids": {
    "voltage": [16,18,19,20,21], "current": [3,22,24], "power_factor": [4,25], 
    "kw": [5], "kva": [7], "demand": [37,38], "communication": [870]
  }
}
}