#!/bin/zsh
# Build the report, let Microsoft Word fill the table of contents and the lists of figures and tables, and export a
# PDF. Word only touches the document it opens here (addressed by name), never other open documents.
#   PY=/path/to/python build/render.sh        (run from capstone_submission/)
set -e
cd "${0:A:h}/.."
PY=${PY:-python3}
DOCX=$($PY build/build_report.py --word | head -1)
W=~/Library/Containers/com.microsoft.Word/Data/Documents/capstone_render
mkdir -p "$W"
rm -f "$W/report.docx" "$W/report.pdf"
cp "$DOCX" "$W/report.docx"
osascript <<EOF
tell application "Microsoft Word"
	open file name "$W/report.docx"
	set d to document "report.docx"
	repeat 2 times
		repeat with i from 1 to 3
			update table of contents i of d
		end repeat
	end repeat
	save d
	save as d file name "$W/report.pdf" file format format PDF
	close document "report.docx" saving no
end tell
EOF
cp "$W/report.docx" "$DOCX"
cp "$W/report.pdf" "${DOCX%.docx}.pdf"
echo "$DOCX"
echo "${DOCX%.docx}.pdf"
