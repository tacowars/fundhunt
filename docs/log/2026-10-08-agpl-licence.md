# fundhunt is licensed AGPL-3.0-or-later

- Date: 2026-10-08
- Links: `LICENSE`

## Decision

fundhunt is released under the GNU Affero General Public License v3.0 or
later.

## Why

The owner's goal is that nobody can take the code into a product they
resell without giving their changes back.

- **Plain GPL-3.0** only binds someone who *distributes* copies. The
  likeliest resale path is a hosted service, like the predecessor
  itself, and that can run modified code without ever distributing it.
- **AGPL-3.0** adds the network clause: users of a modified hosted
  version are entitled to its source.

AGPL is also what the owner's other public project uses, so the two
projects follow the same practice.

## Punted / alternatives

- **MIT or Apache-2.0.** Rejected: they explicitly allow closed resale.
- **GPL-3.0.** Rejected for the SaaS gap described above.
- **A non-commercial licence** such as PolyForm Noncommercial.
  Rejected. It would forbid commercial use outright, including the
  consultancies the tool is for, and it is not open source.
