## Attribution & Dependency Notice

This project is **not** a network protocol of our own invention.

The cross-host communication in ACP-lite is built **on top of [Syncthing](https://github.com/syncthing/syncthing)** —
an open-source continuous file synchronization tool created by **Jakob Borg** and the Syncthing
contributors (started in 2013 by the Swedish developer Jakob Borg; now maintained by the community
together with the Syncthing Foundation, a registered Swedish non-profit).

We did **not** write the synchronization layer, and we claim **no authorship** over it.
What we did is add a thin scripting layer **on top of** Syncthing's existing file-sync mechanism:

- each host runs Syncthing and the agents exchange a single shared folder;
- two hosts become connected by **mutually adding each other's Device ID**;
- from then on, a file written into that folder simply appears on the other host.

Multi-agent collaboration here is therefore **borrowed from Syncthing's mechanism**, not created by us.
We are grateful to the Syncthing project and its maintainers.

ACP-lite itself is released under the **MIT License** (see `LICENSE`).
