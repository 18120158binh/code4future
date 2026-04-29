# Deep Dive: Why Vanilla RAG Fails at Text-to-SQL

To prove that GraphRAG's victory is fundamentally architectural and not LLM bias, we can analyze the exact context vectors pulled during the retrieving phase on "Expert" difficulty queries.

Modern data architectures (like the dbt project used in this benchmark) utilize dimensional modeling (`stg_`, `int_`, `fct_`, `dim_`). This staging structure exposes the critical flaw of Standard Vector RAG.

## Case Study 1: The Churner Analysis (`expert_04`)

**User Query:** 
> *"Find users who were active last month but have had zero sessions this month — potential churners. Include their engagement score and last visit date"*

**Tables Required to write the expected SQL:**
`['rpt_user_engagement', 'fct_sessions', 'dim_users']`

### Vanilla RAG (The Failure)
**Tables Retrieved (Top 5):** `['int_sessions', 'rpt_user_engagement', 'stg_campaigns', 'fct_pageviews', 'rpt_funnel_analysis']`

**The Mechanism of Failure:**
Standard RAG relies strictly on semantic similarity (Nearest Neighbors). 
* "Sessions" semantically matches `int_sessions` higher than `fct_sessions`.
* "Engagement score" perfectly hits `rpt_user_engagement`.
* "Visit" semantically hits `fct_pageviews`.
* **The Result:** The required `fct_sessions` and `dim_users` tables scored just below the Top 5 cutoff. The LLM is provided an `int_sessions` table (an intermediate transformation) and `fct_pageviews`, making it literally impossible to write the final requested query grouping correctly by `dim_users`.

### GraphRAG (The Success)
**Tables Retrieved:** `[..., 'dim_users', 'fct_sessions', 'fct_conversions', 'rpt_user_engagement', 'int_sessions', ...]` (17 tables via graph expansion)

**The Mechanism of Success:**
GraphRAG also initially retrieves `int_sessions` and `rpt_user_engagement` via Vector Search. **However**, it then treats these as "Seed Nodes" and traverses the Neo4j Graph.
* It traces the `DEPENDS_ON` edges defined by your dbt Graph.
* It traces the `FK_REFERENCES` edges where Primary Keys are shared.
Because `rpt_user_engagement` explicitly groups by `user_id`, the graph has an edge pointing directly to `dim_users`. GraphRAG automatically pulls `dim_users` into the context. Because `int_sessions` feeds into `fct_sessions`, GraphRAG pulls `fct_sessions` into context. 
The semantic limitations are entirely bypassed by structural fact.

---

## Case Study 2: Campaign Touches (`expert_05`)

**User Query:** 
> *"For users who made a purchase, show all the campaigns they interacted with leading up to the purchase and the number of touches per campaign"*

**Tables Required:**
`['fct_conversions', 'fct_sessions']`

### Vanilla RAG (The Failure)
**Tables Retrieved:** `['int_sessions', 'stg_users', 'events', 'rpt_funnel_analysis', 'stg_events']`

**The Mechanism of Failure:**
The LLM cannot generate the SQL because it doesn't have the `fct_conversions` table (which tracks 'purchases') nor the `fct_sessions` table (where `utm_campaign` attributes are stored). Pure semantic indexing failed because "purchase" strongly matched `events` and `stg_events` (where raw purchases are tracked), while "campaign" hit `int_sessions`.

### GraphRAG (The Success)
**Tables Retrieved:** `[..., 'campaigns', 'fct_conversions', 'fct_sessions', 'fct_pageviews', ...]`

**The Mechanism of Success:**
By traversing the schema graph starting from `events` and `stg_events`, GraphRAG identified `fct_conversions` (which depends on `events`) as a core structural neighbor. It pulled the final unified Fact tables into context, ensuring the LLM had the exact schema needed to map `utm_campaign` to `first_purchase_at` over Foreign Keys.

## Conclusion

Vanilla RAG operates on the false assumption that **"The table describing the concept is semantically named similarly to the concept."** In highly normalized databases or dbt pipelines, this is almost never true. Users ask questions about abstract "concepts" (like churn, campaigns, conversions), while databases store data via normalized entities and foreign keys.

Because GraphRAG extracts Foreign Key connections and lineage, it effectively bridges the gap between *Semantic Intent* (the Vector Search) and *Database Reality* (the Graph Traversal).
