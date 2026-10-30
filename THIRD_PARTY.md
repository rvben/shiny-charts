# Third-party code and assets

The browser bundle uses Apache ECharts 6.0.0 (Apache-2.0), zrender (BSD-3-Clause),
and tslib. The build preserves linked legal comments and distributes their license
and notice files beside the runtime bundle. See `src/shiny_charts/www/`.

The demo reuses the existing FinOps example's Manrope fonts. They are distributed
under the SIL Open Font License; see `examples/www/OFL.txt`. The chart library
does not ship or prescribe these fonts: it inherits the host application's font.
