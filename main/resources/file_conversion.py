from io import BytesIO, StringIO
import csv
import markdown
import xlwt
import xlrd
from flask import current_app  # fix(clean): remove this
from PIL import Image


# returns a buffer containing a thumbnail image of the given input image (provided in a buffer)
def compute_thumbnail(image_data, width, output_format='JPEG'):
    max_width = width
    max_height = width * 10
    in_stream = BytesIO(image_data)
    image = Image.open(in_stream)
    image.thumbnail((max_width, max_height), Image.ANTIALIAS)
    out_stream = BytesIO()
    image.save(out_stream, format=output_format, quality=80)
    return (out_stream.getvalue(), image.size[0], image.size[1])


# convert markdown to HTML, handling some custom extensions
# fix(clean): move elsewhere?
def process_doc_page(markdown_source):

    # expand markdown into HTML
    html = markdown.markdown(markdown_source)

    # insert images
    file_prefix = current_app.config['DOC_FILE_PREFIX']  # fix(soon): only use images stored within the resource system
    input_lines = html.split('\n')
    output_lines = []
    for line in input_lines:
        if line:
            while '!{' in line:
                start_pos = line.find('!{')
                end_pos = line.find('}', start_pos + 1)
                if end_pos < 0:
                    break
                file_names = line[(start_pos+2):end_pos]
                file_names = file_names.split(',')
                image_link = '<a href="%s/%s"><img src="%s/%s"></a>' % (file_prefix, file_names[1], file_prefix, file_names[0])
                line = line[:start_pos] + image_link + line[(end_pos+1):]
        output_lines.append(line)
    return '\n'.join(output_lines)


# convert a CSV file to an XLS file; input is data contents; output is data contents
def convert_csv_to_xls(data):

    # create CSV reader for the data
    in_stream = StringIO(data)
    reader = csv.reader(in_stream)

    # create Excel workbook
    wb = xlwt.Workbook()
    ws = wb.add_sheet('Sheet1')

    # transfer data into workbook
    for (row_index, row) in enumerate(reader):
        for (col_index, item) in enumerate(row):
            ws.write(row_index, col_index, item)

    # get the workbook file contents
    out_stream = BytesIO()
    wb.save(out_stream)
    return out_stream.getvalue()


# convert an XLS or XLSX file to a CSV; input is data contents; output is data contents
def convert_xls_to_csv(data):

    # create a workbook object and get the first worksheet
    wb = xlrd.open_workbook(file_contents=data)
    ws = wb.sheet_by_index(0)

    # open CSV writer object
    out_stream = StringIO()
    writer = csv.writer(out_stream)

    # read rows
    for i in xrange(ws.nrows):
        row = ws.row_values(i)
        writer.writerow(row)

    # get CSV file data
    return out_stream.getvalue()


# convert line endings to UNIX style (line feeds)
def convert_new_lines(data):
    cr_count = data.count('\r')
    lf_count = data.count('\n')
    if cr_count:
        if lf_count == 0:
            data = data.replace('\r', '\n')  # CR -> LF
        elif lf_count == cr_count:
            data = data.replace('\r', '')  # CRLF -> LF
    return data


# test CSV conversion
# fix(clean): move to a server unit test
def test():
    csv_data = '''a,b,c
1,test1,foo1
2,test2,foo2
3,test3,foo3
4,test4,foo4
'''
    xls_data = convert_csv_to_xls(csv_data)
    csv_gen_data = convert_xls_to_csv(xls_data)
    print(csv_gen_data)
    print(str(csv_gen_data).strip() == str(csv_data).strip())  # fix(later): probably doens't match due to newlines

    #csvData = convert_xls_to_csv(open('test.xlsx', 'rb').read())
    #print(csvData)


if __name__ == '__main__':
    test()
