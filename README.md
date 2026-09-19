# CodeBase Time Machine

**CodeBase Time Machine** is a software engineering tool that helps developers understand how a codebase evolved over time.

Instead of only showing what the code looks like today, it analyzes the history of a public GitHub repository to explain:

- when code was introduced
- how functions and classes changed
- why certain changes were made
- which pull requests and issues are connected to those changes
- how different parts of the codebase depend on each other
- how the architecture of the project changed over time

It acts like a **time machine for a software repository**.

Phase 9 also provides a deterministic investigation workspace for stack traces, suspected fix
commits, known-good/known-bad ranges, and individual source lines. It ranks evidence-backed commit
candidates, supports conservative SZZ analysis and manual static bisect, and never executes code
from the analyzed repository.

---

## What does it do?

A developer provides a public GitHub repository URL.

CodeBase Time Machine then analyzes the repository and builds a historical view of the project using:

- Git commits
- file changes
- source code
- functions and classes
- pull requests
- issues
- comments and code reviews
- dependency relationships
- architecture information
- local AI using Ollama

The goal is to help developers understand not only:

> **What does this code do?**

but also:

> **Why does this code exist?**

---

## Main Features

### Git History Explorer

CodeBase Time Machine reads the Git history of the repository and allows users to explore:

- commits
- commit authors
- changed files
- additions and deletions
- file renames
- tags
- commit diffs
- repository history

This creates the foundation for understanding how the project developed over time.

---

### Code Explorer

The application analyzes the current source code and provides a repository browser.

It can detect structures such as:

- functions
- classes
- methods
- constructors
- interfaces
- enums
- structs
- modules
- imports

The code explorer allows users to browse files, inspect symbols, search the repository, and understand the structure of the project.

Supported languages include:

- Python
- JavaScript
- TypeScript
- TSX
- Java
- C
- C++
- Go
- PHP

---

## Code History and Time Travel

CodeBase Time Machine tracks the history of individual functions, classes, methods, and files.

For example:

```text
get_user()

    ↓ modified

get_user()

    ↓ renamed

find_user()

    ↓ moved

UserService.find_user()
```

For a symbol, the system can identify:

- when it was introduced
- which commit introduced it
- who introduced it
- when its body changed
- when its signature changed
- when it was renamed
- when it was moved
- when it was deleted
- when it was reintroduced

Users can also view older versions of source code and compare historical versions.

---

## GitHub Pull Requests and Issues

Git history tells us **what changed**, but pull requests and issues often explain **why it changed**.

CodeBase Time Machine connects repository history with public GitHub development information such as:

- pull requests
- issues
- labels
- PR descriptions
- issue descriptions
- comments
- review comments
- commits inside pull requests

This allows relationships such as:

```text
Issue #17
    ↓
Pull Request #42
    ↓
Commit abc123
    ↓
UserService.find_user()
```

This makes it easier to understand the reason behind a piece of code.

---

## Dependency Graph

CodeBase Time Machine analyzes relationships between different parts of the repository.

It can identify relationships such as:

```text
Controller
    ↓
Service
    ↓
Repository
    ↓
Model
```

The dependency graph can include:

- imports
- function calls
- inheritance
- file dependencies
- module dependencies
- external package dependencies

The graph can be explored visually.

---

## Impact Analysis

Before changing an important function or file, developers can inspect which parts of the repository may depend on it.

For example:

```text
PaymentService
      ↑
CheckoutController
      ↑
CheckoutPage
```

If `PaymentService` changes, CodeBase Time Machine can show the code that may potentially be affected.

This helps developers understand the possible impact of a change before modifying the code.

---

## Code Hotspots

The application can identify areas of the repository that are both frequently changed and structurally important.

Hotspot information can consider:

- number of changes
- number of contributors
- incoming dependencies
- outgoing dependencies
- dependency importance
- historical activity

A hotspot does **not** mean that the code is bad.

It simply identifies code that may deserve additional attention because it changes often or is important to other parts of the project.

---

## Change Coupling

Some files may not directly import each other but may repeatedly change together in the same commits.

CodeBase Time Machine detects these relationships.

For example:

```text
auth_controller.py
        ↕
auth_service.py
```

If these files frequently change together, they may have an important logical relationship that is not obvious from static dependencies alone.

---

## Circular Dependency Detection

The dependency graph can also detect circular relationships such as:

```text
Module A
   ↓
Module B
   ↓
Module C
   ↓
Module A
```

These cycles can be displayed and inspected in the architecture view.

---

# Software Archaeology

CodeBase Time Machine also performs deeper historical analysis of the repository.

For a function, class, file, or module, it can analyze:

- code age
- original name
- original location
- number of modifications
- renames
- moves
- major rewrites
- contributors
- stability
- volatility
- deleted code
- historical versions

This helps developers investigate where code originally came from and how it reached its current form.

---

## Code Provenance

For a symbol such as:

```text
UserService.find_user()
```

CodeBase Time Machine may reconstruct a history like:

```text
Introduced as:
get_user()

src/users.py

        ↓

Renamed:
find_user()

        ↓

Moved:
src/services/user_service.py

        ↓

Major rewrite

        ↓

Current:
UserService.find_user()
```

This provides a complete historical identity for important code.

---

## Deleted Code Search

Code that no longer exists can still be important when understanding old commits or design decisions.

CodeBase Time Machine can search historical symbols and files that have been deleted.

Examples include:

- deleted functions
- deleted classes
- old file names
- renamed functions
- previous implementations

Users can inspect their last known source code and history.

---

## Historical Contributors

The system analyzes which contributors have historically worked on different parts of the codebase.

For a file or symbol it can show:

- contributors
- number of historical changes
- contribution frequency
- recent activity
- introduction history

These metrics represent repository activity only.

They are not intended to measure developer skill or organizational ownership.

---

# Architecture Explorer

CodeBase Time Machine automatically builds a high-level view of the repository architecture.

For example:

```text
Frontend
    ↓
API
    ↓
Services
    ↓
Repositories
    ↓
Database
```

Users can explore architecture at different levels:

```text
Component
    ↓
Module
    ↓
File
    ↓
Symbol
```

This makes large repositories easier to understand.

---

# Architecture Time Machine

One of the main features of CodeBase Time Machine is the ability to inspect how software architecture changed over time.

Instead of viewing only the current architecture, users can inspect historical architecture snapshots.

Example:

```text
2023

Controller
    ↓
Service
    ↓
Repository
```

Later:

```text
2025

Controller ─────────→ Repository
    ↓
Service
    ↓
Repository
```

CodeBase Time Machine can identify when architectural relationships were introduced or removed.

---

## Architecture Comparison

Two points in repository history can be compared.

For example:

```text
v1.0
vs
v2.0
```

The comparison can show:

- modules added
- modules removed
- dependencies added
- dependencies removed
- cycles introduced
- cycles resolved
- component changes
- architecture metric changes

---

## Architecture Drift

Users can select an architecture snapshot as a baseline.

CodeBase Time Machine can then compare the current architecture against that baseline.

It may show:

```text
Baseline
    ↓
Current Architecture

+ 4 modules
- 1 module

+ 12 dependencies
- 3 dependencies

+ 1 dependency cycle
```

Architecture drift represents **structural change**.

It does not automatically mean the architecture became worse.

---

## Architecture Rules

Users can define simple architectural rules.

For example:

```text
Controller
    ↓ allowed
Service

Service
    ↓ allowed
Repository
```

and:

```text
Controller
    ✕
Repository
```

If a direct `Controller → Repository` dependency appears, CodeBase Time Machine can detect it.

It can also determine:

- when the relationship first appeared
- which commit introduced it
- which pull request was related
- when the violation was later removed

---

# AI-Powered Repository Questions

CodeBase Time Machine includes a local AI assistant powered by **Ollama**.

The AI runs locally and uses repository evidence collected by the system.

Users can ask questions such as:

```text
Why does this function exist?
```

```text
Why was this condition added?
```

```text
When was this class introduced?
```

```text
Which PR introduced this behavior?
```

```text
What issue caused this change?
```

```text
What depends on this service?
```

```text
What could be affected if I change this?
```

```text
How did this module evolve?
```

```text
When did this architecture dependency appear?
```

---

## Evidence-Grounded AI

The AI does not simply inspect the current source code.

It retrieves evidence from:

```text
Git commits
      +
Symbol history
      +
Diffs
      +
Pull requests
      +
Issues
      +
Reviews
      +
Git blame
      +
Dependency graph
      +
Architecture history
```

This information is retrieved using a combination of:

- deterministic relationships
- normal text search
- semantic search
- vector embeddings

The relevant evidence is then provided to the local Ollama model.

---

## Example

A developer selects:

```python
if user is None:
    return None
```

and asks:

```text
Why does this check exist?
```

CodeBase Time Machine may discover:

```text
Code line
    ↓
Git blame
    ↓
Commit abc123
    ↓
Pull Request #42
    ↓
Issue #17
```

and produce an answer explaining that the check was introduced while fixing the issue described in that pull request.

The answer also includes links to the supporting evidence.

If the repository does not contain enough evidence to determine the reason, CodeBase Time Machine says that the reason is unknown rather than inventing an explanation.

---

# Local AI

CodeBase Time Machine uses **Ollama** instead of a paid cloud AI API.

Example configuration:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434

OLLAMA_LLM_MODEL=qwen3:4b
OLLAMA_EMBEDDING_MODEL=all-minilm
```

Example models currently used during development:

```text
qwen3:4b
all-minilm
```

The AI layer is optional.

Repository analysis, Git history, code browsing, architecture, and historical analysis continue working even when Ollama is not running.

---

# Technology Stack

## Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- TanStack Query
- React Flow

## Backend

- Python
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic

## Database

- PostgreSQL
- pgvector

## Repository Analysis

- Git
- Tree-sitter
- NetworkX

## AI

- Ollama
- Local LLM
- Local embedding model
- Retrieval-Augmented Generation (RAG)

## Optional Background Processing

- Redis
- Celery

CodeBase Time Machine can also run locally without Redis or Celery.

---

# How It Works

The overall pipeline looks like this:

```text
Public GitHub Repository
          ↓
      Git Analysis
          ↓
   Static Code Analysis
          ↓
    Symbol History
          ↓
 PR / Issue Context
          ↓
   Dependency Graph
          ↓
 Architecture Analysis
          ↓
 Software Archaeology
          ↓
Architecture History
          ↓
  Evidence Documents
          ↓
 Local Embeddings
          ↓
 PostgreSQL + pgvector
          ↓
  Hybrid Retrieval
          ↓
       Ollama
          ↓
Grounded Explanation
```

---

# Running the Project

## Requirements

Install:

- Git
- Python
- Node.js
- PostgreSQL
- pgvector

For AI features also install:

- Ollama

Docker is not required for normal local development.

---

## Backend

From the backend directory:

```cmd
cd /d "D:\swe project\backend"
```

Activate the Python virtual environment:

```cmd
.venv\Scripts\activate
```

Start FastAPI:

```cmd
uvicorn app.main:app --reload
```

The backend runs at:

```text
http://localhost:8000
```

API documentation:

```text
http://localhost:8000/docs
```

---

## Frontend

Open another terminal:

```cmd
cd /d "D:\swe project\frontend"
```

Run:

```cmd
npm run dev
```

The application runs at:

```text
http://localhost:3000
```

---

## Ollama

Make sure Ollama is running.

Check installed models:

```cmd
ollama list
```

Example:

```text
qwen3:4b
all-minilm
```

Check Ollama:

```cmd
curl http://localhost:11434/api/tags
```

Check CodeBase Time Machine AI connection:

```cmd
curl http://localhost:8000/api/system/ai-status
```

---

# Environment Configuration

Create a `.env` file locally.

Important variables include:

```env
DATABASE_URL=

GITHUB_TOKEN=

LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=qwen3:4b
OLLAMA_EMBEDDING_MODEL=all-minilm

TASK_EXECUTION_MODE=local
```

Use the included:

```text
.env.example
```

as a reference.

Never commit your real `.env` file because it may contain passwords or tokens.

---

# GitHub Access

CodeBase Time Machine currently analyzes **public GitHub repositories only**.

A GitHub token is optional.

Without a token, GitHub's unauthenticated API rate limits apply.

With a server-side token:

```env
GITHUB_TOKEN=...
```

the application can perform more GitHub API requests.

The token is used only by the backend and should never be exposed to the frontend.

---

# Security

Repositories are treated as untrusted input.

CodeBase Time Machine does **not**:

- execute repository source code
- run repository scripts
- run repository tests
- install repository dependencies
- execute binaries from analyzed repositories
- modify analyzed repositories
- push commits
- create pull requests

Repository analysis is based on Git data and static source-code analysis.

---

# Current Scope

CodeBase Time Machine currently focuses on:

- public GitHub repositories
- repository history
- static code analysis
- code evolution
- pull request and issue context
- dependency analysis
- impact analysis
- software archaeology
- architecture analysis
- architecture evolution
- local AI-assisted repository understanding

Private repository access is not currently supported.

---

# Project Goal

Modern codebases contain years of decisions that are difficult to understand from source code alone.

A developer may find code like:

```python
if strange_condition:
    do_something_unexpected()
```

The current code tells us **what happens**.

CodeBase Time Machine tries to answer:

```text
Why was this added?

Who added it?

When was it added?

What problem was being solved?

Which issue or pull request discussed it?

How has it changed since then?

What other code depends on it?

What would potentially be affected if it changed?

How did the surrounding architecture evolve?
```

The goal is to make software history easier to explore and help developers understand not only **what a codebase is**, but **how and why it became that way**.
