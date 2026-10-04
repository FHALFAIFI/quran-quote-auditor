#!/bin/sh
# Rebuilds the two DOCX files in this folder from their sources (our own text, written for these tests), with real word processors:
#   lo-article.docx        ← lo-article.fodt by LibreOffice (tracked deletion + insertion, a footnote, a tab, a line break, an empty paragraph)
#   textutil-article.docx  ← textutil-article.html by macOS textutil (Apple's DOCX writer)
# Run from this folder: sh make.sh   (needs soffice and, on macOS, textutil). The outputs are committed so the tests need neither.
set -e
cd "$(dirname "$0")"
soffice --headless --convert-to 'docx:MS Word 2007 XML' lo-article.fodt --outdir .
textutil -convert docx textutil-article.html -output textutil-article.docx
