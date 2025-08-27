# Bunny Hunter

Bunny Hunter is a small collection of Python tools and agents that work together to search second‑hand markets and find good deals.

## Project layout

- `00-main-agent` – LangGraph based orchestrator.  It uses OpenAI models to search listings, estimate a reasonable price and compose an inquiry.  Helper containers are invoked via Docker.
- `01-search-list` – scraper that queries [당근마켓](https://www.daangn.com/) for past or current listings.  Results are written as JSON to stdout.  It expects environment variables such as `ITEM_NAME`, `MODE` (`ALL` or `CURRENT`) and an optional `REGION`.
- `02-gpt-oss-20b-ollama` – forwards a prompt to an Ollama instance running the `gpt-oss:20b` model.  The prompt is supplied via the `PROMPT` environment variable and the response is emitted as JSON.

## Requirements

- Python 3.10+ (repository tested with Python 3.12)
- Docker for running the helper containers
- An OpenAI API key available as `OPENAI_API_KEY` or in a `.env` file for the main agent

Install dependencies for the main agent with:

```bash
pip install -r 00-main-agent/requirements.txt
```

## Running

1. Build the helper containers:

```bash
docker build -t search-list 01-search-list
docker build -t gpt-oss-20b-ollama 02-gpt-oss-20b-ollama
```

2. Run the agent:

```bash
cd 00-main-agent
python app.py "아이폰 14 프로"
```

The agent will look up past transactions, estimate a reasonable price and poll for matching deals.  A suggested inquiry message is printed when a candidate is found.

## License

No license file is provided.

