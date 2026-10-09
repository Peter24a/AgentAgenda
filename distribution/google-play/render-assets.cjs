const fs = require('node:fs');
const path = require('node:path');

process.env.FONTCONFIG_FILE = path.join(__dirname, 'fontconfig.conf');
const sharp = require('sharp');

async function main() {
  const assets = path.join(__dirname, 'assets');
  await sharp(path.join(assets, 'app-icon.svg'))
    .resize(512, 512)
    .ensureAlpha()
    .png()
    .toFile(path.join(assets, 'app-icon-512.png'));
  await sharp(path.join(assets, 'feature-graphic.svg'))
    .resize(1024, 500)
    .removeAlpha()
    .png()
    .toFile(path.join(assets, 'feature-graphic-1024x500.png'));
  const records = [];
  for (const file of ['app-icon-512.png', 'feature-graphic-1024x500.png']) {
    const pathname = path.join(assets, file);
    const {width, height, channels, format} = await sharp(pathname).metadata();
    const bytes = fs.statSync(pathname).size;
    records.push({file, width, height, channels, format, bytes});
    if (file.startsWith('app-icon') && (width !== 512 || height !== 512 || channels !== 4 || bytes > 1024 * 1024)) throw Error('Invalid app icon');
    if (file.startsWith('feature-graphic') && (width !== 1024 || height !== 500 || channels !== 3)) throw Error('Invalid feature graphic');
  }
  fs.writeFileSync(path.join(assets, 'verification.json'), JSON.stringify(records, null, 2) + '\n');
  console.log(JSON.stringify(records));
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
