#!/usr/bin/env python3
#
# Script for converting reMarkable tablet ".rm" files to SVG image.
# this works for the new *.rm format, where each page is a separate file
# credits to
# https://github.com/lschwetlick/maxio/tree/master/tools
# which in turn credits
# https://github.com/jmiserez/maxio/blob/ee15bcc86e4426acd5fc70e717468862dce29fb8/tmp-rm16-ericsfraga-rm2svg.py
#

import sys
import struct
import os.path
import argparse
import re


__prog_name__ = "rm2svg"
__version__ = "0.0.2.1"


# Size
default_x_width = 1404
default_y_width = 1872

# Mappings
stroke_colour = {
    0 : "black",
    1 : "grey",
    2 : "white",
}
'''stroke_width={
    0x3ff00000 : 2,
    0x40000000 : 4,
    0x40080000 : 8,
}'''


# because i'm to lazy to replace all output.write calls. Do this in the future lol
class OutputStrHack:
    def __init__(self):
        self.svgfile = ""
    def write(self,str):
        self.svgfile+=str

def set_coloured_annots():
    global stroke_colour
    stroke_colour = {
        0: "blue",
        1: "red",
        2: "white",
        3: "yellow"
    }


def abort(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def rm2svg(data, coloured_annotations=False,
           x_width=default_x_width, y_width=default_y_width):
    # Read the file in memory. Consider optimising by reading chunks.
    if coloured_annotations:
        set_coloured_annots()

    #with open(input_file, 'rb') as f:
    #    data = f.read()
    offset = 0

    # Is this a reMarkable .lines file?
    
    expected_header=b'reMarkable .lines file, version=#          '
    if len(data) < len(expected_header) + 4:
        abort('File too short to be a valid file')

    fmt = '<{}sI'.format(len(expected_header))
    header, nlayers = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
    # print('header={} nlayers={}'.format(header, nlayers))
    re_expected_header = f"^{str(expected_header,'utf-8').replace('#','([345])')}$"
    re_expected_header_match = re.match(re_expected_header, str(header ,'utf-8'))
    if (re_expected_header is None) or (nlayers < 1):
        abort('Not a valid reMarkable file: <header={}> <nlayers={}'.format(header, nlayers))
    _stroke_fmt_by_vers = {
        '3': '<IIIfI',
	'5': '<IIIfII' }
    _stroke_fmt = _stroke_fmt_by_vers[re_expected_header_match.groups(1)[0]]
    output = OutputStrHack()
    output.write('<svg xmlns="http://www.w3.org/2000/svg" height="{}" width="{}">'.format(y_width, x_width)) # BEGIN Notebook
    output.write('''
        <script type="application/ecmascript"> <![CDATA[
            var visiblePage = 'p1';
            function goToPage(page) {
                document.getElementById(visiblePage).setAttribute('style', 'display: none');
                document.getElementById(page).setAttribute('style', 'display: inline');
                visiblePage = page;
            }
        ]]> </script>
    ''')

    # Iterate through pages (There is at least one)
    output.write('<g id="p1" style="display:inline">')
    # Iterate through layers on the page (There is at least one)
    for layer in range(nlayers):
        # print('New layer')
        fmt = '<I'
        (nstrokes,) = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)

        # print('nstrokes={}'.format(nstrokes))
        # Iterate through the strokes in the layer (If there is any)
        for stroke in range(nstrokes):
            fmt = _stroke_fmt
            stroke_data = struct.unpack_from(fmt, data, offset)
            offset += struct.calcsize(fmt)
            pen, colour, i_unk, width = stroke_data[:4]
            nsegments = stroke_data[-1]
            # print('pen={} colour={} i_unk={} width={} nsegments={}'.format(pen,colour,i_unk,width,nsegments))
            opacity = 1
            last_x = -1.; last_y = -1.
            #if i_unk != 0: # No theory on that one
                #print('Unexpected value at offset {}'.format(offset - 12))
            if pen == 0 or pen == 1:
                pass # Dynamic width, will be truncated into several strokes
            elif pen == 2 or pen == 4: # Pen / Fineliner
                width = 32 * width * width - 116 * width + 107
            elif pen == 3: # Marker
                width = 64 * width - 112
                opacity = 0.9
            elif pen == 5: # Highlighter
                width = 30
                opacity = 0.2
                if coloured_annotations:
                    colour = 3
            elif pen == 6: # Eraser
                width = 1280 * width * width - 4800 * width + 4510
                colour = 2
            elif pen == 7: # Pencil-Sharp
                width = 16 * width - 27
                opacity = 0.9
            elif pen == 8: # Erase area
                opacity = 0.
            else: 
                opacity = 1

            width /= 2.3 # adjust for transformation to A4
            
            #print('Stroke {}: pen={}, colour={}, width={}, nsegments={}'.format(stroke, pen, colour, width, nsegments))
            output.write('<polyline style="fill:none;stroke:{};stroke-width:{:.3f};opacity:{}" points="'.format(stroke_colour[colour], width, opacity)) # BEGIN stroke

            # Iterate through the segments to form a polyline
            for segment in range(nsegments):
                fmt = '<ffffff'
                xpos, ypos, pressure, tilt, i_unk2, j_unk2 = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                # print('(x,y)=({},{})'.format(xpos,ypos))
                #xpos += 60
                #ypos -= 20
                ratio = (y_width/x_width)/(1872/1404)
                if ratio > 1:
                    xpos = ratio*((xpos*x_width)/1404)
                    ypos = (ypos*y_width)/1872
                else:
                    xpos = (xpos*x_width)/1404
                    ypos = (1/ratio)*(ypos*y_width)/1872
                if pen == 0:
                    if 0 == segment % 8:
                        segment_width = (5. * tilt) * (6. * width - 10) * (1 + 2. * pressure * pressure * pressure)
                        #print('    width={}'.format(segment_width))
                        output.write('" />\n<polyline style="fill:none;stroke:{};stroke-width:{:.3f}" points="'.format(
                                    stroke_colour[colour], segment_width)) # UPDATE stroke
                        if last_x != -1.:
                            output.write('{:.3f},{:.3f} '.format(last_x, last_y)) # Join to previous segment
                        last_x = xpos; last_y = ypos
                elif pen == 1:
                    if 0 == segment % 8:
                        segment_width = (10. * tilt -2) * (8. * width - 14)
                        segment_opacity = (pressure - .2) * (pressure - .2)
                        #print('    width={}, opacity={}'.format(segment_width, segment_opacity))
                        output.write('" /><polyline style="fill:none;stroke:{};stroke-width:{:.3f};opacity:{:.3f}" points="'.format(
                                    stroke_colour[colour], segment_width, segment_opacity)) # UPDATE stroke
                        if last_x != -1.:
                            output.write('{:.3f},{:.3f} '.format(last_x, last_y)) # Join to previous segment
                        last_x = xpos; last_y = ypos

                output.write('{:.3f},{:.3f} '.format(xpos, ypos)) # BEGIN and END polyline segment

            output.write('" />\n') # END stroke

    # Overlay the page with a clickable rect to flip pages
    output.write('<rect x="0" y="0" width="{}" height="{}" fill-opacity="0"/>'.format(x_width, y_width))
    output.write('</g>') # Closing page group
    output.write('</svg>') # END notebook
    return output.svgfile
