# Architecture diagram

The diagram shows the main parts of the lab. Keep addresses, hostnames,
ports, hardware details, and service inventories out of it.

Adapted from [Goblinmine/homelab-diagram](https://github.com/Goblinmine/homelab-diagram)
under the [MIT license](LICENSE).

## Render

Install Fira Sans and Fira Code. Use rsvg-convert or ImageMagick with SVG support.

```sh
cd docs/diagram
python3 build.py             # writes the SVG and PNG
python3 build.py --optimize  # also compresses the PNG
```

Do not hand-edit the PNG.
