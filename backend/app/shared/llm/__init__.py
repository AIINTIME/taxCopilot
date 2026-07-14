"""Provider-agnostic LLM abstraction. services/rag/llm_client.py is the ONLY
file under services/ allowed to import from this package, and it must only
import router.get_llm_provider() / base types -- never a provider module
directly.
"""
