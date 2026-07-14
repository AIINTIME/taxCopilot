"""Text embedding for ingested chunks.

Open design question, not yet resolved: an embedding call needs some
provider's SDK, but this codebase's only SDK-import rule (see
app/shared/llm/) covers text-generation providers (LLMProvider.generate()),
not embeddings. Rather than import an embedding SDK directly here -- which
would sit outside the shared/llm/ provider-isolation pattern -- this stays
unimplemented until an embedding-provider abstraction is designed
(e.g. a parallel EmbeddingProvider interface under shared/llm/, or a
dedicated shared/embeddings/ package). No SDK is imported in this file.
"""


def embed_texts(texts: list[str]) -> list[list[float]]:
    raise NotImplementedError(
        "TODO: wire an embedding provider once the provider-agnostic "
        "pattern is extended to cover embeddings, not just text generation"
    )
