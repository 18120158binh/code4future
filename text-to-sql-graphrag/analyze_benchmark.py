import json

def analyze():
    with open('tests/evaluation/benchmark_results.json', 'r') as f:
        data = json.load(f)

    rag_matches = 0
    gr_matches = 0
    total_required = 0
    
    rag_avg_tables = 0
    gr_avg_tables = 0

    results = data["results"]
    
    for c in results:
        rag_avg_tables += len(c['rag']['tables_in_context'])
        gr_avg_tables += len(c['graphrag']['tables_in_context'])
        
        # In the dry run, the "missing_tables" from the eval indicates ALL target tables (since generated_sql = target_sql)
        # Wait, inside evaluate_single, it compares generated tables with expected tables. 
        # If generated == expected, missing_tables is EMPTY.
        # Oh, meaning the target tables are NOT missing_tables. Target tables are found in the query itself!
        # The true target tables are actually extracted during eval. How do I get them?
        pass
