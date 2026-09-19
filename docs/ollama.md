# Local Ollama setup

Codebase Time Machine uses Ollama directly over its local HTTP API. It has no cloud AI fallback and does
not require Ollama for Code, History, Commits, Pull Requests, Issues, or Architecture.

1. Install Ollama for Windows from the official Ollama installer and start the Ollama application.
2. Choose one chat model and one embedding model that fit the machine. Model names are examples,
   not requirements: a smaller chat model can reduce memory use, while embedding models such as
   `nomic-embed-text` or `mxbai-embed-large` offer different vector dimensions.
3. Pull the exact names selected for `.env`:

   ```cmd
   ollama pull YOUR_CHAT_MODEL
   ollama pull YOUR_EMBEDDING_MODEL
   ```

4. Configure the root `.env`:

   ```dotenv
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_LLM_MODEL=YOUR_CHAT_MODEL
   OLLAMA_EMBEDDING_MODEL=YOUR_EMBEDDING_MODEL
   OLLAMA_REQUEST_TIMEOUT_SECONDS=60
   ```

5. Check Ollama and Codebase Time Machine:

   ```cmd
   curl http://localhost:11434/api/tags
   curl http://localhost:8000/api/system/status
   curl http://localhost:8000/api/system/ai-status
   ```

When the backend runs in Docker, use `http://host.docker.internal:11434`. The native `npm run dev`
launcher translates that hostname to `127.0.0.1` automatically.

The embedding dimension is discovered from model output during indexing and stored with the model
and index-version identifier. Changing `OLLAMA_EMBEDDING_MODEL` makes existing repository AI
indexes incompatible. Open **Ask** and rebuild the index; vectors from different models or
dimensions are never mixed. A large repository can require substantial time and memory on its
first embedding run. Later runs reuse documents whose normalized content hash has not changed.
The general system status reports `ollama: ok` or `unavailable` without making Ollama a required
backend dependency. The dedicated AI status also reports whether each configured model is installed.
Ollama's `:latest` suffix is accepted for a model configured without a tag, such as `all-minilm`.
Repository AI indexing is started manually from **Ask** or **Overview** after repository analysis;
existing repositories are not automatically re-indexed.

Common states:

- **Ollama is not running:** start the Ollama application and retry.
- **Model is not installed:** pull the exact configured model name.
- **AI index has not been built:** open a repository's Ask page and select **Build AI index**.
- **Request timed out:** choose a model that fits available memory or increase the request timeout.
