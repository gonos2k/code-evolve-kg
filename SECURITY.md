# Security Policy

## Untrusted Code Warning

This repository contains research code for evolving and evaluating generated
programs. The current evaluator provides resource containment only. It is not a
security boundary.

Do not run untrusted LLM-generated candidates on a sensitive host with this
snapshot alone. A production or shared environment must add an external sandbox
or jail that provides at least:

- network deny by default
- read-only filesystem except for an isolated work directory
- environment-variable allowlist
- non-privileged UID/GID
- process, CPU, memory, and file-size limits
- syscall filtering or an equivalent policy
- cleanup of all child processes and temporary files

The current Fortran evaluator removes only a small set of known API-related
environment variables. That is not sufficient to protect credentials or local
files on a host running untrusted code.

## Supported Use

The current tree is suitable for trusted local research and development review.
It is not production-ready for executing hostile code or for making security
claims about isolation.

## Reporting

Open a private security issue or contact the repository owner before publishing
details of a vulnerability that could expose credentials, local files, or host
resources.
