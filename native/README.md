# shiny-charts-native

Experimental optional Rust accelerator for shiny-charts 0.5.0b1.
Install `shiny-charts[native]==0.5.0b1` and opt in with
`from shiny_charts.native import chart`.

Retains Polars Arrow columns and performs validation, categorical packing and
JSON serialization in Rust. Regular CPython 3.10+ is supported through abi3;
free-threaded Python is not covered. Other unsupported platforms can build from
the source distribution with a recent Rust compiler and maturin.

The native path handles integer, Float64, boolean, string and null fields for
bar, line, area and scatter charts. Untyped all-null columns and other types/inputs and pie/histogram use the
existing Python builder. The renderer still uses Shiny's JSON envelope and adds
an inner JSON parse in the browser. This beta is intended for pilot feedback,
not a claim of improved whole-dashboard latency.
