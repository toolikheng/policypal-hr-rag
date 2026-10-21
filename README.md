# PolicyPal — AI HR Policy Assistant

PolicyPal answers employee questions about HR policies in plain English, cites the
policy document and section it used, and refuses to guess when the policies don't
cover a question. It uses retrieval-augmented generation (RAG) with a local
embedding model, PostgreSQL + pgvector, and a local LLM through Ollama.

> All policy documents in this repository are **fictional sample data** for a
> made-up company, **Binaan Maju Sdn Bhd**. They are not real company policies
> and are not legal advice.

**Status:** work in progress. This README will document setup, architecture and
measured evaluation results as each part is built.
