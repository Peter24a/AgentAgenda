const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const sharp = require('sharp');

const root = path.resolve(__dirname, '../..');
const source = path.join(__dirname, 'source');
const android = path.join(root, 'apps/mobile/android/app/src/main/res');
const play = path.join(root, 'distribution/google-play/assets');
const read = name => fs.readFileSync(path.join(source, name), 'utf8');
const write = (file, value) => {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  fs.writeFileSync(file, value);
};

async function main() {
  const provenance = JSON.parse(fs.readFileSync(path.join(__dirname, 'sources.json')));
  for (const item of provenance.sources) {
    const hash = crypto.createHash('sha256').update(read(item.file)).digest('hex');
    if (hash !== item.sha256) throw Error(`Official source changed: ${item.file}`);
  }
  const white = read('sara_isotipo_blanco.svg');
  const symbol = white.match(/<g id="sara-isotipo">[\s\S]*<\/g>/)?.[0];
  if (!symbol) throw Error('Missing official symbol');
  const glyph = `<g transform="translate(76 121) scale(0.5) translate(-150 -70)">${symbol}</g>`;
  const fullBleed = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512"><title>AgentAgenda · isotipo oficial SARA</title><rect width="512" height="512" fill="#6B4F73"/>${glyph}</svg>\n`;
  write(path.join(play, 'app-icon.svg'), fullBleed);
  // Play supplies its own rounded mask. Web and legacy Android retain the
  // official rounded container, with transparent (never white) outer corners.
  const rounded = read('sara_app_icon_morado.svg');
  write(path.join(root, 'apps/web/public/assets/brand.svg'), rounded);
  write(path.join(root, 'apps/web/privacy/agentagenda/brand.svg'), rounded);
  for (const [density, size] of Object.entries({mdpi: 48, hdpi: 72, xhdpi: 96, xxhdpi: 144, xxxhdpi: 192})) {
    const file = path.join(android, `mipmap-${density}/ic_launcher.png`);
    await sharp(Buffer.from(rounded)).resize(size, size).ensureAlpha().png().toFile(file);
  }

  // Keep the exact four Bezier paths. Scale the entire mark as one object to
  // fit Android's central 66dp safe circle on the 108dp adaptive canvas.
  const scale = 0.82;
  const inset = 256 * (1 - scale);
  const paths = [...white.matchAll(/<path fill="#FFFFFF" d="([^"]+)" transform="translate\(([^,]+),([^\)]+)\)"\s*\/>/g)];
  if (paths.length !== 4) throw Error('Expected four official paths');
  const vectorPaths = paths.map(([, d, x, y]) => `      <group android:translateX="${x}" android:translateY="${y}"><path android:fillColor="#FFFFFFFF" android:pathData="${d.trim()}" /></group>`).join('\n');
  const vector = `<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="108dp" android:height="108dp" android:viewportWidth="512" android:viewportHeight="512">\n  <group android:scaleX="${scale}" android:scaleY="${scale}" android:translateX="${inset}" android:translateY="${inset}">\n    <group android:scaleX="0.5" android:scaleY="0.5" android:translateX="1" android:translateY="86">\n${vectorPaths}\n    </group>\n  </group>\n</vector>\n`;
  write(path.join(android, 'drawable/ic_launcher_foreground.xml'), vector);
  write(path.join(android, 'values/brand_colors.xml'), '<?xml version="1.0" encoding="utf-8"?>\n<resources><color name="ic_launcher_background">#6B4F73</color></resources>\n');
  for (const api of [26, 33]) {
    write(path.join(android, `mipmap-anydpi-v${api}/ic_launcher.xml`), `<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n  <background android:drawable="@color/ic_launcher_background" />\n  <foreground android:drawable="@drawable/ic_launcher_foreground" />\n${api >= 33 ? '  <monochrome android:drawable="@drawable/ic_launcher_foreground" />\n' : ''}</adaptive-icon>\n`);
  }
  const foreground = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><g transform="translate(${inset} ${inset}) scale(${scale})">${glyph}</g></svg>`;
  const {data, info} = await sharp(Buffer.from(foreground)).ensureAlpha().raw().toBuffer({resolveWithObject: true});
  let maxRadius = 0;
  for (let y = 0; y < info.height; y++) for (let x = 0; x < info.width; x++) {
    if (data[(y * info.width + x) * 4 + 3] > 0) maxRadius = Math.max(maxRadius, Math.hypot(x + 0.5 - 256, y + 0.5 - 256));
  }
  const safeRadius = 512 * 33 / 108;
  if (maxRadius > safeRadius) throw Error(`Mark escapes Android safe circle: ${maxRadius} > ${safeRadius}`);
  write(path.join(__dirname, 'validation.json'), JSON.stringify({sourcePaths: paths.length, geometry: 'Exact official path data and translations', android: {canvasDp: 108, safeCircleDiameterDp: 66, markMaxRadiusDp: maxRadius * 108 / 512, adaptive: true, monochrome: true}, play: {container: 'Full bleed; Play applies the mask', symbolTransform: 'translate(76 121) scale(0.5) translate(-150 -70)'}}, null, 2) + '\n');
  console.log(`Official branding exported; adaptive mark radius ${(maxRadius * 108 / 512).toFixed(2)}dp / 33dp`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
