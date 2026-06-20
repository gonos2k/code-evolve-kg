# CodeEvolve TODOs

## Literature-Driven Roadmap

### Demonstrate WRF single-physics capability

The WRF direction is currently designed and scaffolded, not demonstrated. Ship
one runnable `wrf_single_physics` problem with an exact WRF source commit or
digest, one selected scheme, standalone train/holdout boundary fixtures,
reference parity against the original WRF scheme, baseline correctness and speed
numbers, and an accepted-candidate host-smoke procedure.

### Add diversity pressure to search

Embeddings can be generated, but they are not currently used for novelty,
selection, migration, or MAP-Elites descriptors. Add novelty-aware parent
selection, diversity-aware migration quotas, and meaningful descriptors such as
embedding distance, AST/code-shape features, or domain metrics so quality and
diversity are not collapsed into scalar fitness.

### Measure KG grounding as a component

Run same-seed, same-budget ablations with KG context/gate enabled and disabled.
Report best fitness, median fitness, accepted-candidate rate, compile/error
rate, and best-fitness-per-model-call. Keep declared knowledge use separate from
verified use so the experiment can falsify, not just support, the KG benefit
claim.

### Improve sample efficiency

The current loop is mostly one generated candidate per evaluation epoch. Add
cheap rejection sampling for malformed or policy-invalid outputs and a reward
bandit over model ensemble members, prompts, or mutation strategies. Report
accepted/evaluated candidates per model call.

### Add reflection and evaluator attestation

Add a reflection record that converts failure diagnostics into next mutation
hypotheses. Separately, make problem evaluators declare which gates they enforce
such as correctness, finite-number checks, input immutability, train/holdout
split, and semantic acceptance policy. The core should record this declaration
and surface missing gates in metadata.

### Add multi-objective reporting

Keep scalar fitness for simple examples, but have scientific runs emit the
objective vector separately: speed ratio, absolute and relative error,
conservation or budget metrics, fixture failure rate, and code-size or
maintainability proxies when relevant.

## New Features

### Multiple file support

This feature has two independent steps: allowing the agent to read multiple input files when needed, and allowing the agent to modify multiple files. The former essentially boils down to implementing an agentic logic similar to what cursor or claude code does (allow agent to run bash scripts and see the output). This would require a significant refactor of the llm logic, and this would also be a challenge for smaller models like qwen to handle. The latter step is not that difficult: we could for instance ask the SEARCH/REPLACE blocks to also identify which file they are targeted at. This would however add further complexity to the instructions the LLM needs to do.

### Full rewrite

Allow the agent to do a full rewrite of the target file. This should be simple to implement.

## Systems

### Overhaul of the evaluation logic (Done)

Here's an overview of the current situation as potential issues: currently, each island has a separate process, and each process can call the evaluator function to run a given solution. Thus, if we have N islands, there may be N parallel processes competing for CPU/Mem resources to run the solution. The solution itself may want to use all CPUs, so this can get a bit messy and unfair, since our evaluator timeout measures wall-clock time.

**Fix 1 implemented:** The `resource_monitor` thread (previously `mem_monitor`) now also tracks accumulated CPU time (user + system) across the entire process tree via `psutil`. When the total CPU time exceeds `timeout_s`, the process is killed with a `CPUTimeExceededError`. This makes timeouts fairer under CPU contention — a program that is CPU-starved gets its full budget of actual computation rather than being killed early by a wall-clock timer. It also catches multi-threaded or multi-process evaluations that burn more CPU time than wall-clock time.

**Fix 2 implemented:** Users can now set `num_cpus_per_eval` in `BUDGET_CONFIG`. When set, CodeEvolve partitions the available CPUs (as reported by `os.sched_getaffinity`) into consecutive slices and pins each island process to its own slice via `os.sched_setaffinity` at startup. This eliminates cross-island CPU contention and makes wall-clock time roughly equal to CPU time, removing the need for a separate CPU-time budget. Requires Linux; falls back gracefully with a warning on other platforms or when insufficient CPUs are available.

### Better SEARCH/REPLACE

Even with more expensive LLMs, we get a lot of SEARCH/REPLACE errors, i.e., LLM trying to search for a block of code that does not perfectly match the parent program. We should think of a way of minimizing these kinds of errors (something that happened quite often with GEMINI 2.5 was it trying to search for a code block that almost matched the parent program, apart from an hallucinated comment).

## Quality-of-life

### More templates for system messages

Instead of asking the users to specify the evaluation budgets, installed packages, etc, we should automatically format those and add them to the system message.

### Better config structure

All configs within the code are dicts. This can get quite confusing and hard to read. We should implement dataclasses with these configs and defaults. This is conceptually easy, but would require a major refactor of the code.

### Better dependency handling for problems

Each benchmark problem should have its own dependencies, and they should be installed whenever the problem is first run. Currently, we bundle all dependencies into CodeEvolve itself, which isn't great.

## Unit tests

The current suite covers core utilities, KG context and gate behavior, Graphify
export, Fortran toolchain/problem evaluation, and multiple negative-path cases.
Remaining gaps are broader end-to-end evolution runs with the MOCK LLM setting,
runnable WRF fixtures, isolation-layer tests, and wider type-check coverage.
