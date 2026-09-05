# Shared data contracts

This directory is the language-neutral contract between the Python backend
and the frontend. `posture.json` is the source of truth for pressure-matrix
dimensions, posture labels and action mappings. `pressure-frame.schema.json`
describes a matrix transported over HTTP.

Changing an existing ID, matrix orientation or field meaning is a breaking
change and requires a contract-version update plus coordination with all team
members.

The frontend can obtain the validated posture contract at runtime from
`GET /api/contracts/posture`; it does not need filesystem access to this
directory.
