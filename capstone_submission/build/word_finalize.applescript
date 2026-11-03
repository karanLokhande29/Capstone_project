-- Opens the report in Microsoft Word, updates the table of contents, list of figures and list of tables,
-- then saves the .docx in place and exports a PDF next to it. Touches only the document it opened (by name).
on run argv
	set docPath to item 1 of argv
	set pdfPath to item 2 of argv
	set docName to item 3 of argv
	tell application "Microsoft Word"
		open file name docPath
		set d to document docName
		repeat 2 times
			repeat with t in (tables of contents of d)
				update t
			end repeat
		end repeat
		save d
		save as d file name pdfPath file format format PDF
		close document docName saving no
	end tell
end run
