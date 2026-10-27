# TrackMyExpense — Remote MCP Expense Server

A production-style **Model Context Protocol (MCP) server** for managing personal expenses and budgets through AI clients.

TrackMyExpense exposes expense-management capabilities as MCP tools and resources, allowing MCP-compatible clients such as Claude Desktop to interact with a persistent PostgreSQL database through natural language.

The project was initially developed and tested locally and is now deployed as a **remote MCP server using Streamable HTTP**, with PostgreSQL hosted remotely.

---

## Architecture

```text
                    ┌─────────────────────┐
                    │     MCP Client      │
                    │  Claude / Inspector │
                    └──────────┬──────────┘
                               │
                               │ MCP
                               │ Streamable HTTP
                               ▼
                    ┌─────────────────────┐
                    │  TrackMyExpense     │
                    │    MCP Server       │
                    │      FastMCP        │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Expense / Budget   │
                    │      Tools          │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   psycopg Pool      │
                    │  Connection Pool    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     PostgreSQL      │
                    │   Remote Database   │
                    └─────────────────────┘
```

---

## What is MCP?

The **Model Context Protocol (MCP)** is a protocol that allows AI applications to interact with external tools and data sources through a standardized interface.

Instead of putting all application logic inside an AI application, capabilities can be exposed through MCP:

```text
AI Client
    ↓
MCP
    ↓
Tool
    ↓
Application Logic
    ↓
Database / External API
```

TrackMyExpense uses this pattern to expose expense-management operations to an MCP client.

---

## Features

### Expense Management

The server supports operations such as:

- Add an expense
- Retrieve an expense
- List expenses
- Filter expenses by date
- Update expenses
- Soft-delete expenses
- Generate category-based summaries

Example expense:

```json
{
  "amount": 200,
  "category": "Travelling",
  "date": "2026-09-26",
  "note": "Cab"
}
```

### Budget Management

The server also supports budget-related operations including:

- Creating budgets
- Retrieving budgets
- Updating budgets
- Tracking budget information by category and month

### MCP Resources

Read-only application information can be exposed through MCP resources, allowing clients to retrieve structured contextual data without treating every operation as a mutation.

---

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python |
| MCP Framework | FastMCP |
| Protocol | Model Context Protocol |
| Remote Transport | Streamable HTTP |
| Database | PostgreSQL |
| Database Driver | psycopg 3 |
| Connection Pooling | psycopg_pool |
| Configuration | python-dotenv |
| Package Management | uv |
| MCP Client | Claude Desktop |
| Testing / Inspection | MCP Inspector |
| Deployment | Remote MCP hosting |

---

## Project Structure

```text
TrackMyExpenseMCP/
│
├── server.py
├── pyproject.toml
├── uv.lock
├── README.md
└── .env
```

The current implementation intentionally keeps the MCP server logic in a single file while the project is being used to learn and validate MCP concepts end-to-end.

---

## Database

The application uses PostgreSQL for persistent storage.

### Expenses

The expense model contains fields such as:

```text
id
date
amount
category
subcategory
note
created_at
updated_at
deleted_at
```

### Budgets

Budget records contain:

```text
id
category
month
amount
created_at
updated_at
```

The application uses a PostgreSQL connection pool rather than creating a new database connection for every MCP tool invocation.

---

## Connection Pool

The server uses `psycopg_pool`:

```python
pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=5,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    },
)
```

This keeps database connection management separate from the MCP tool layer.

---

## Running Locally

### Prerequisites

- Python 3.12
- uv
- PostgreSQL
- An MCP-compatible client

### Install dependencies

```bash
uv sync
```

### Configure environment variables

Create a `.env` file:

```env
DATABASE_URL=postgresql://<username>:<password>@<host>:<port>/<database>
```

### Start the server

For remote-style HTTP transport:

```bash
uv run python server.py
```

The server starts using FastMCP's Streamable HTTP transport.

---

## Testing with MCP Inspector

MCP Inspector can be used to inspect and test the server independently of an AI client.

Example:

```bash
npx @modelcontextprotocol/inspector uv run fastmcp run server.py
```

This makes it possible to inspect:

- Available tools
- Tool schemas
- Resources
- Tool inputs
- Tool outputs
- MCP protocol communication

This was useful during development because it separates **MCP protocol problems** from **application/database problems**.

---

## Claude Desktop

The MCP server can be connected to an MCP-compatible client such as Claude Desktop.

Once connected, the client can discover the available tools and invoke them based on the user's request.

For example:

```text
"Add ₹200 for travelling on September 26 with the note Cab."
```

The AI client can translate the request into the appropriate MCP tool invocation:

```text
Claude
   ↓
add_expense(...)
   ↓
TrackMyExpense MCP Server
   ↓
PostgreSQL
```

---

## Remote MCP

The project was initially developed locally and later deployed as a remote MCP server.

The remote architecture is:

```text
Claude Desktop
       │
       │ MCP / Streamable HTTP
       ▼
Remote TrackMyExpense Server
       │
       │ PostgreSQL connection
       ▼
Remote PostgreSQL Database
```

This demonstrates the difference between:

### Local MCP

```text
Claude
  ↓
stdio
  ↓
Local MCP Server
  ↓
Local Database
```

and:

### Remote MCP

```text
Claude
  ↓
HTTP
  ↓
Remote MCP Server
  ↓
Remote PostgreSQL
```

---

## Database Schema Evolution

One practical issue encountered during deployment was schema compatibility.

The initial database already contained an `expenses` table, so:

```sql
CREATE TABLE IF NOT EXISTS expenses (...)
```

did not add newly introduced columns.

For example, the application expected:

```text
created_at
updated_at
deleted_at
```

but the existing database schema did not contain them.

The issue was resolved using migration-style `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements.

This reinforced an important backend lesson:

> `CREATE TABLE IF NOT EXISTS` prevents creation errors; it does not migrate an existing schema.

For a larger production system, a dedicated migration framework such as Alembic would be preferable.

---

## Key MCP Concepts Demonstrated

This project was built to understand MCP beyond simply creating a tool.

### Tools

Tools represent actions the AI client can invoke.

Examples:

```text
add_expense
get_expense
list_expenses
update_expense
delete_expense
```

### Resources

Resources expose read-only contextual data through MCP resource URIs.

### Transport

The project uses:

```text
Streamable HTTP
```

for remote MCP communication.

### MCP Client

Claude Desktop acts as an MCP client and discovers the server's capabilities.

### Persistence

The MCP tools operate against PostgreSQL rather than maintaining application state only in memory.

---

## What I Learned

Building this project helped me understand several layers of an AI application architecture:

- MCP protocol fundamentals
- MCP tools and resources
- Tool schemas and structured inputs
- Local vs remote MCP
- stdio vs Streamable HTTP
- MCP client/server communication
- PostgreSQL connection pooling
- Remote database connectivity
- Database schema evolution
- MCP Inspector-based debugging
- Connecting an AI client to application capabilities

The most important takeaway was that **MCP is an integration layer between AI applications and existing software capabilities**.

The expense tracker itself is relatively simple. The interesting part of the project was building the complete path:

```text
AI Client
    ↓
MCP Protocol
    ↓
Remote MCP Server
    ↓
Application Tools
    ↓
Connection Pool
    ↓
PostgreSQL
```

---

## Future Improvements

Potential next steps:

- Split the server into service/repository layers
- Introduce Alembic database migrations
- Add authentication/authorization for remote MCP
- Add structured logging
- Add automated tests
- Add MCP server observability
- Add more analytics tools
- Add recurring expenses
- Add spending insights
- Containerize the deployment
- Add CI/CD

---

## Project Goal

The goal of TrackMyExpense is not simply to build an expense tracker.

It is a hands-on project for understanding how **AI applications can securely interact with real backend services through MCP**, while applying familiar backend engineering concepts such as APIs, connection pooling, persistence, schema evolution, and deployment.

---

## Author

Built as part of my hands-on exploration of:

**Generative AI · AI Agents · MCP · Tool Calling · LangGraph · Backend Engineering**
