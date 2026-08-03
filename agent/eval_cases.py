"""Task-specific verification cases from the team ambiguity/out-of-scope checklist.

These are not the full Week 3 evaluation set. They capture the concrete
Lec/Aditi verification questions from `Transit Group Project Ambiguous
Questions_complete_1.pdf` so the team can list them, dry-run the reporting
format without Claude, and later run the same cases live once an Anthropic key
is available.
"""

EVAL_CASES = [
    # Lec: 5-10 additional question variations / rephrasings.
    {
        "question": "When are the next few Red Line trains coming into Metro Center?",
        "expected_tools": ["get_real_time_arrivals"],
        "expected_args": {"get_real_time_arrivals": {"station": "Metro Center"}},
        "notes": "Rephrase of the Week 1 live-arrivals example.",
        "category": "lec_variation",
    },
    {
        "question": "How long until the next train at Gallery Place?",
        "expected_tools": ["get_real_time_arrivals"],
        "expected_args": {"get_real_time_arrivals": {"station": "Gallery Place"}},
        "notes": "Live arrival variation with a different station / short station name.",
        "category": "lec_variation",
    },
    {
        "question": "Any issues on the Red Line at the moment?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Red"}},
        "notes": "Rephrase of the service-alert example.",
        "category": "lec_variation",
    },
    {
        "question": "Is the Blue Line experiencing any disruptions right now?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Blue"}},
        "notes": "Rephrase of the service-alert example.",
        "category": "lec_variation",
    },
    {
        "question": "Are there any systemwide Metro delays right now?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {}},
        "notes": "Alert lookup without a specific line.",
        "category": "lec_variation",
    },
    {
        "question": "How's the weather looking outside at the moment?",
        "expected_tools": ["get_weather"],
        "expected_args": {"get_weather": {"when": "now"}},
        "notes": "Rephrase of the weather example.",
        "category": "lec_variation",
    },
    {
        "question": "What's the weather looking like for my commute tomorrow morning?",
        "expected_tools": ["get_weather"],
        "expected_args": {"get_weather": {"when": "tomorrow"}},
        "notes": "Forecast variation instead of current weather.",
        "category": "lec_variation",
    },
    {
        "question": "Should I bike or take the train tomorrow morning?",
        "expected_tools": ["get_weather", "get_service_alerts"],
        "expected_args": {"get_weather": {"when": "tomorrow"}, "get_service_alerts": {}},
        "notes": "Multi-tool commute question: weather plus service alerts.",
        "category": "lec_variation",
    },
    {
        "question": "Would it make more sense to bike or ride the train in tomorrow?",
        "expected_tools": ["get_weather", "get_service_alerts"],
        "expected_args": {"get_weather": {"when": "tomorrow"}, "get_service_alerts": {}},
        "notes": "Rephrase of the multi-tool commute case.",
        "category": "lec_variation",
    },
    {
        "question": "How do I get from Dupont Circle to Union Station, and are there any delays?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {}},
        "notes": "Multi-part route/trip question plus current service-alert check.",
        "category": "lec_variation",
    },

    # Aditi: ambiguous station/line references from the complete PDF.
    {
        "question": "When's the next train at Court House?",
        "expected_tools": ["get_real_time_arrivals"],
        "expected_args": {"get_real_time_arrivals": {"station": "Court House"}},
        "notes": "Station served by multiple lines; live arrivals may include Orange and Silver trains.",
        "category": "aditi_ambiguity",
    },
    {
        "question": "Is the Blue Line delayed near the stadium stop?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Blue"}},
        "notes": "Common station description should map to Stadium-Armory context without fabricating arrivals.",
        "category": "aditi_ambiguity",
    },
    {
        "question": "Is Metro Ctr on the Red Line running normally?",
        "expected_tools": ["get_service_alerts"],
        "expected_args": {"get_service_alerts": {"line": "Red"}},
        "notes": "Common abbreviation for Metro Center; should state/handle assumption clearly.",
        "category": "aditi_ambiguity",
    },
    {
        "question": "How long until the next Silver Line train at Largo?",
        "expected_tools": ["get_real_time_arrivals"],
        "expected_args": {"get_real_time_arrivals": {"station": "Largo"}},
        "notes": "Station short form for Downtown Largo with a specific line constraint in the question.",
        "category": "aditi_ambiguity",
    },
    {
        "question": "Is the Purple Line delayed today?",
        "expected_tools": [],
        "expected_args": {},
        "notes": "Purple Line is not a Metrorail line; should ask/redirect rather than using Metrorail tools.",
        "category": "aditi_ambiguity",
    },

    # Lec: out-of-scope stress test, specifically Metrobus vs. Metrorail.
    {
        "question": "What time does the D40 bus come?",
        "expected_tools": [],
        "expected_args": {},
        "notes": "Metrobus route schedule is out of scope for this Metrorail-only project.",
        "category": "lec_out_of_scope_metrobus",
    },
    {
        "question": "Is the D74 Rhode Island Av-Foggy BottomGo running on time?",
        "expected_tools": [],
        "expected_args": {},
        "notes": "Metrobus live status is out of scope; no rail tool should be called.",
        "category": "lec_out_of_scope_metrobus",
    },
    {
        "question": "Where's the closest Metrobus stop to Dupont Circle?",
        "expected_tools": [],
        "expected_args": {},
        "notes": "Metrobus stop location is out of scope; no rail tool should be called.",
        "category": "lec_out_of_scope_metrobus",
    },
]
