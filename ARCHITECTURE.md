# Architecture

Planning is a deterministic pure calculation over immutable `ItemState`, `Offer` and `PlanningPolicy` values. Feasibility and score evidence are retained on the recommendation; approval is a separate stateful boundary. A locked supplier narrows the feasible pool before scoring. The approval service creates only a draft reference and never conducts a 1C document.
