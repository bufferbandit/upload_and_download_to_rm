#!/usr/bin/python3

# https://github.com/libvips/libvips/issues/1438

import sys
import pyvips
import ctypes    


def crop_poly(image, *points):
    # crop to bounding box
    x, y = zip(*points)
    left = min(x)
    top = min(y)
    crop = image.crop(left, top, max(x) - left, max(y) - top)

    # make alpha channel ... svgload makes a 4-band image, we want
    # the alpha from that

    svg = f"""
        <svg viewBox="0 0 {crop.width} {crop.height}">
            <polygon style="fill: white; stroke: none" points="
    """
    svg += " ".join([f"{x - left}, {y - top} " for x, y in points])
    svg += """
            "/>
        </svg>
    """

    alpha = pyvips.Image.svgload_buffer(bytes(svg, "ascii"))[3]
    joined = crop.bandjoin(alpha)
    return joined


               
def create_rectangle(start_corner,x_length,y_length):
    left_top     = start_corner
    right_top    = [ start_corner[0]+x_length,   start_corner[1]        ]
    left_bottom  = [ start_corner[0], start_corner[1]+y_length          ]
    right_bottom = [ start_corner[0]+x_length, start_corner[1]+y_length ] 
    return [left_top,right_top,left_bottom,right_bottom]



def crop_image(svg_image,start_corner,x_length,y_length):

    image = pyvips.Image.new_from_buffer(svg_image.encode("utf-8"),"", access="sequential")
    rectangle = create_rectangle(start_corner,x_length,y_length)
    cropped_image = crop_poly(image,*rectangle)
    return cropped_image
