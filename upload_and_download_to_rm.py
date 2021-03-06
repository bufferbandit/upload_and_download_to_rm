#!/usr/bin/python3
import os
import sys
import json
import time
import img2pdf
import requests
import tempfile
from io import BytesIO
from uuid import uuid4
from librM2svg import rm2svg
from configparser import ConfigParser
from zipfile import ZipFile, ZIP_DEFLATED


from lib_svg_crop import crop_image
import numpy


#cropped_image = crop_image(svg,[85,270],55,55)
#cropped_image.write_to_file("funcout1.png")


CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "upload_and_download_to_rm.cfg")

REGISTRATION_URL = "https://my.remarkable.com/token/json/2/device/new"
REFRESH_URL = "https://my.remarkable.com/token/json/2/user/new"

# Yes, apparently this is actually the url used by reMarkable...
SERVICE_DISCOVERY_URL = "https://service-manager-production-dot-remarkable-production.appspot.com/service/json/1/document-storage?environment=production&group=auth0%7C5a68dc51cb30df3877a1d7c4&apiVer=2"
PRESUMED_SERVICE_URL = "https://document-storage-production-dot-remarkable-production.appspot.com"

# Changing this probably breaks things, even if you're not on Windows
DEVICE_DESC = "desktop-windows"


def register_device(connect_code, device_id):
    headers = {"Authorization": "Bearer"}
    payload = {
        "code": connect_code,
        "deviceDesc": DEVICE_DESC,
        "deviceID": device_id
    }
    r = requests.post(REGISTRATION_URL, headers=headers,
                      data=json.dumps(payload))
    if r.status_code != 200:
        print("Device registration failed (invalid code?):")
        print(f"{r.status_code}: {r.text}")
        sys.exit()
    return r.text


def refresh_token(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(REFRESH_URL, headers=headers)
    if r.status_code != 200:
        print("Refreshing token failed")
        print(f"{r.status_code}: {r.text}")
        sys.exit()
    return r.text


def service_discovery():
    r = requests.get(SERVICE_DISCOVERY_URL)
    if r.status_code != 200:
        print("Service discovery failed, but let's still try using the presumed url!")
        return PRESUMED_SERVICE_URL
    return json.loads(r.text)['Host']


def upload_img(fname, url=PRESUMED_SERVICE_URL):
    display_name = fname.split("\\")[-1]
    with tempfile.TemporaryFile() as temp:
        temp.write(img2pdf.convert([fname]))
        temp.seek(0)
        upload_pdf(temp.read(), display_name, url)


def upload_pdf(
        pdf_file,
        display_name="UploadedFile",
        url=PRESUMED_SERVICE_URL):
    # Make an upload request
    headers = {"Authorization": f"Bearer {token}"}
    payload = [{
        "ID": str(uuid4()),
        "Type": "DocumentType",
        "Version": 1
    }]
    r = requests.put(
        f"{url}/document-storage/json/2/upload/request",
        headers=headers,
        data=json.dumps(payload)
    )
    if r.status_code != 200:
        print("Upload request failed")
        print(f"{r.status_code}: {r.text}")
        return
    resp = json.loads(r.text)

    doc_id = resp[0].get("ID", None)
    blob_url = resp[0].get("BlobURLPut", None)

    # Upload file to returned BlobURL
    rm_zip = BytesIO()
    content = {
        "extraMetadata": {},
        "fileType": "pdf",
        "lastOpenedPage": 0,
        "lineHeight": -1,
        "margins": 0,
        "pageCount": 1,
        "textScale": 1,
        "transform": {}
    }
    with ZipFile(rm_zip, "w", ZIP_DEFLATED) as zf:
        zf.writestr(f"{doc_id}.pdf", pdf_file)
        zf.writestr(f"{doc_id}.content", json.dumps(content))
        zf.writestr(f"{doc_id}.pagedata", "")
    rm_zip.seek(0)

    r2 = requests.put(blob_url, headers=headers, data=rm_zip.read())
    if not r2.ok:
        return

    # Apparently it's required to update metadata for the file to become
    # visible ?
    metadata = {
        "ID": doc_id,
        "Parent": "",
        "VissibleName": display_name,
        "LastModified": str(round(time.time() * 1000)),
        "Type": "DocumentType",
        "Version": 1
    }
    r3 = requests.put(
        f"{url}/document-storage/json/2/upload/update-status",
        headers=headers,
        data=json.dumps([metadata])
    )
    return r3.ok


def upload(fname):
    if fname.lower().endswith(".pdf"):
        with open(fname, "rb") as f:
            return upload_pdf(f.read(), display_name=fname)
    elif fname.lower().endswith((".jpg", ".png", ".tiff")):
        return upload_img(fname)
    else:
        print("Unsupported filetype: {fname}")


def list_files(url=PRESUMED_SERVICE_URL):
    headers = {"Authorization": f"Bearer {token}"}
    payload = [{
        "ID": str(uuid4()),
        "Type": "DocumentType",
        "Version": 1
    }]
    r = requests.get(
        f"{url}/document-storage/json/2/docs?withBlob=true",
        headers=headers)
    return r.json()


def get_file(filename, url=PRESUMED_SERVICE_URL):
    for file in list_files(url):
        if file["VissibleName"] == filename:
            return file


def download_file_as_blob(file={}, filename="", url=PRESUMED_SERVICE_URL):
    if not file:
        file = get_file(filename)
    if not filename:
        filename = file["VissibleName"]
    blob_url = file["BlobURLGet"]
    blob = requests.get(blob_url, stream=True)
    return blob.content


def save_downloaded_blob_file(blob):
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
        temp_file.write(blob)
        temp_file.close()
        return temp_file.name


def blob_file_to_ZipFile(blob):
    filebytes = BytesIO(blob)
    return ZipFile(filebytes)


def extract_rm_files_from_blob_in_memory(blob):
    zip = blob_file_to_ZipFile(blob)
    return get_svg_files_from_zip(zip)


def extract_rm_files_from_blob_on_disk(blob):
    filename = save_downloaded_blob_file(blob)
    zip = ZipFile(filename)
    return get_svg_files_from_zip(zip)


def get_svg_files_from_zip(zip):
    for file in zip.namelist():
        if file.split("/")[1:] and file.endswith(".rm"):
            rMfile = zip.read(file)
            yield rm2svg(rMfile)

def get_svg_files_from_blob(blob ,memory=True):
    if memory:return extract_rm_files_from_blob_in_memory(blob)
    else:return extract_rm_files_from_blob_on_disk(blob)

def get_pages_as_svg(filename):
    file = get_file(filename)
    blob = download_file_as_blob(file)
    for svg in get_svg_files_from_blob(blob):
        yield svg

def get_page_nr_as_svg(filename,pagenr,start=0):
    for count,page in enumerate(get_pages_as_svg(filename),start=start):
        if count == start:return page


def process_svg_page(svg):
    x_axis = 85
    for count in range(16): # BUG, THE CROPPING IS NOT RIGHT YET
        y_axis = (70 + (count + 2 ) * 100) - 0
        checkbox_img = crop_image(svg,[85,y_axis],55,55)
        checkbox_img.write_to_file(f"checkbox_{count+1}.png")
        checked = checkbox_is_checked(checkbox_img)
        print(f"count={count+1} | checked={checked} | y-axis={y_axis} | size={checkbox_img.get('width')}x{checkbox_img.get('height')}")

def checkbox_is_checked(checkbox_img):
    numpy_img = numpy.frombuffer(
            checkbox_img.write_to_memory(),dtype="int8")
    return bool(numpy.count_nonzero(numpy_img == 1))
    




if __name__ == "__main__":
    config = ConfigParser()
    if not os.path.isfile(CONFIG_FILE_PATH):
        print("No config file found")
        device_id = str(uuid4())
        code = input("Please enter the code from https://my.remarkable.com/connect/remarkable\n> ")
        token = register_device(code, device_id)
        config["SETTINGS"] = {
            "DEVICE_ID": device_id,
            "TOKEN": token
        }
        with open(CONFIG_FILE_PATH, "w") as config_file:
            config.write(config_file)
        print("Config file ('upload_and_download_to_rm.cfg') generated, next time you won't be prompted")
    else:
        config.read(CONFIG_FILE_PATH)

    device_id = config["SETTINGS"]["DEVICE_ID"]
    token = config["SETTINGS"]["TOKEN"]
    token = refresh_token(token)
    
    for svg_page in get_pages_as_svg("checklist"):
        checked = process_svg_page(svg_page)
        print(checked)
        break
   
    
