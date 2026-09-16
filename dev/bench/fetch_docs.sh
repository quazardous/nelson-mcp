#!/usr/bin/env bash
# fetch_docs.sh — download the bench's source documents and convert them.
#
# The documents are real, openly licensed, and big enough to hurt:
#   moby-dick.odt           Project Gutenberg #2701 (public domain), 135 chapters
#   gdpr.docx               EU Regulation 2016/679 from EUR-Lex (public), Word format
#   owid-co2.xlsx           Our World in Data CO2 dataset (CC-BY), 50k rows × 79 cols
#   scBigSingleSheet2000.ods  LibreOffice's own perf test document (MPL)
#
# Only the URLs live in git; the files are regenerated here, under docs/.
# Conversion runs in a throwaway profile with an English locale, so the
# documents are not tagged with the host's language (a French host tags them
# fr-FR, and the full-text index then stems English text as French).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/src"; DOCS="$HERE/docs"
PROFILE="$(mktemp -d /tmp/nelson-bench-convert-XXXXXX)"
mkdir -p "$SRC" "$DOCS"
trap 'rm -rf "$PROFILE"' EXIT

fetch() { [ -s "$SRC/$2" ] || curl -fsSL -o "$SRC/$2" "$1"; echo "  $2"; }

echo "Downloading sources"
fetch "https://www.gutenberg.org/cache/epub/2701/pg2701-images.html"                    moby-dick.html
fetch "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679"        gdpr.html
fetch "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"         owid-co2.csv
fetch "https://raw.githubusercontent.com/LibreOffice/core/master/sc/qa/perf/testdocuments/scBigSingleSheet2000.ods" scBigSingleSheet2000.ods

echo "Converting"
S=(env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 soffice --headless --norestore
   "-env:UserInstallation=file://$PROFILE")
"${S[@]}" --infilter="HTML (StarWriter)" --convert-to odt --outdir "$DOCS" "$SRC/moby-dick.html" >/dev/null
"${S[@]}" --infilter="HTML (StarWriter)" --convert-to 'docx:MS Word 2007 XML' --outdir "$DOCS" "$SRC/gdpr.html" >/dev/null
"${S[@]}" --infilter="CSV:44,34,76,1" --convert-to 'xlsx:Calc MS Excel 2007 XML' --outdir "$DOCS" "$SRC/owid-co2.csv" >/dev/null
cp "$SRC/scBigSingleSheet2000.ods" "$DOCS/"
ls -la "$DOCS"
