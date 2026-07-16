"""Curated, labeled example queries used by the embedding-based fallback in
intent_classifier.py. Each entry is (query_text, intent). Kept as plain data
-- no logic here -- so it's easy to extend with real user queries over time
without touching the classifier itself.
"""

from app.services.query.intent_classifier_types import Intent

COMPUTATION_EXAMPLES = [
    "Calculate our MAT liability for this year",
    "What is our tax payable under Section 115BAA?",
    "Compute the depreciation on our new plant and machinery",
    "How much additional depreciation can we claim on new equipment?",
    "Break down the extra depreciation we can claim on new equipment",
    "Work out our regime comparison between old and new tax rates",
    "What would our capital gains tax be on this property sale?",
    "Give me the exact AMT liability for our LLP",
    "Tell me our total tax outgo for this financial year",
    "What's the WDV of our machinery block after this year's additions?",
    "How much MAT do we owe on a book profit of 90 lakhs?",
    "Calculate the surcharge and cess on our normal tax liability",
    "What is the exact figure we need to pay under 115JB?",
    "Determine whether 115BAA or the normal regime saves us more tax",
    "Work out the indexed cost of acquisition for our land sale",
    "What's our short-term capital gains tax on the shares we sold?",
    "Compute the depreciation allowed on the new machinery we bought",
    "How much tax do we save by switching to the concessional regime?",
    "What is the final tax payable after comparing MAT and normal tax?",
    "Give me a number for our alternate minimum tax liability",
    "What's our net depreciation this year after disposals?",
    "Figure out the exact rupee amount of our regime comparison savings",
]

RETRIEVAL_EXAMPLES = [
    "What is Section 115BAA?",
    "Explain the conditions for claiming additional depreciation",
    "What does the Income Tax Act say about MAT credit carry forward?",
    "Which companies are eligible for the 115BAB concessional rate?",
    "What are the conditions to opt for the new manufacturing regime?",
    "Explain how the capital gains rate changed after July 2024",
    "What is the definition of book profit under Section 115JB?",
    "Tell me about the grandfathering provision for capital gains",
    "What does Schedule III say about depreciation methods?",
    "Explain the difference between short-term and long-term capital gains",
    "What are the exemptions available under Section 54EC?",
    "Describe the eligibility criteria for Section 115BAB",
    "What is the statutory definition of a new manufacturing company?",
    "Explain what happens if we don't opt for the concessional regime",
    "What provisions apply to GST reconciliation for corporate filers?",
    "Tell me what qualifies as plant and machinery for depreciation purposes",
    "What is the effective date of the Income Tax Act 2025?",
    "Explain the evidence required to claim indexation benefit",
    "What are the compliance requirements under Section 115JC?",
    "Describe the audit requirements for companies opting into 115BAA",
    "What does the law say about carry-forward of MAT credit?",
    "Explain the difference between Section 115BAA and 115BAB",
    # Statutory rate/threshold lookups -- a fixed fact quotable directly from
    # the law, not a company-specific figure requiring the computation
    # engine. Distinct from "what is OUR tax liability" (COMPUTATION,
    # above) even though both are phrased as "what is the rate ...".
    "What is the applicable base tax rate for a domestic company if its turnover does not exceed Rs 400 crore?",
    "What is the surcharge rate applicable to companies with income above Rs 10 crore?",
    "What is the standard corporate tax rate for a domestic company under the normal provisions?",
    "What is the applicable rate of Health and Education Cess on corporate tax?",
    "What is the TDS rate applicable on payments to a resident contractor?",
    "What is the threshold turnover limit for a company to qualify for the 25% tax rate?",
    "What is the tax rate available to a domestic company opting for the concessional regime under Section 115BAA, and what condition attaches to that rate?",
    "What concessional rate is available to a new manufacturing domestic company under Section 115BAB, and what is the stated policy objective?",
    "From what date does MAT under Section 115JB become a final tax, and what is the applicable rate?",
    "Under thin capitalisation rules, what is the EBITDA-based cap on interest deductibility for payments to associated enterprises?",
]

BOTH_EXAMPLES = [
    "What's our MAT liability and is this treatment defensible under 115JB?",
    "Explain Section 115BAA and tell me if it would save us money",
    "What are the depreciation rules and how much can we claim this year?",
    "Tell me about the regime comparison rules and calculate which is better for us",
    "Explain the capital gains rate change and compute our tax under the new rate",
    "What does 115JC require and what would our AMT liability be?",
    "Describe the conditions for 115BAB and calculate our tax if we qualify",
    "Explain indexation and work out our indexed capital gains",
    "What's the additional depreciation rule and how much do we get this year?",
    "Tell me the MAT provisions and compute our exact liability",
    "Explain grandfathering and calculate our gain under it",
    "What are the surcharge slabs and what would ours be this year?",
    "Describe Schedule III depreciation and compute our WDV closing balance",
    "Explain 115BAA conditions and tell me our tax if we switch",
    "What's the definition of book profit and what's ours after adjustments?",
]

INTENT_EXAMPLES: list[tuple[str, Intent]] = (
    [(text, Intent.COMPUTATION) for text in COMPUTATION_EXAMPLES]
    + [(text, Intent.RETRIEVAL) for text in RETRIEVAL_EXAMPLES]
    + [(text, Intent.BOTH) for text in BOTH_EXAMPLES]
)
