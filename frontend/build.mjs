import { build } from 'esbuild';
import { copyFileSync } from 'node:fs';
await build({
  entryPoints: ['frontend/index.js'],
  outfile: 'src/shiny_charts/www/shiny-charts.js',
  bundle: true,
  minify: true,
  format: 'iife',
  target: ['es2020'],
  legalComments: 'linked',
});
copyFileSync('node_modules/echarts/LICENSE', 'src/shiny_charts/www/ECHARTS-LICENSE.txt');
copyFileSync('node_modules/echarts/NOTICE', 'src/shiny_charts/www/ECHARTS-NOTICE.txt');
copyFileSync('node_modules/zrender/LICENSE', 'src/shiny_charts/www/ZRENDER-LICENSE.txt');
