import argparse
import json
import multiprocessing
import os
import requests


def get_uuid(filename):

    files_endpt = 'https://api.gdc.cancer.gov/files'
    # params = {'fields':'cases.submitter_id,file_id,file_name,file_size'}
    # print(filename)
    filt = {
        "op":"=",
        "content":{
            "field":"file_name",
            "value":[
                # "TCGA-3C-AALI-01Z-00-DX2.CF4496E0-AB52-4F3E-BDF5-C34833B91B7C.svs"
                filename
            ]
        }
    }
    params = {'fields':'file_name', 'filters':json.dumps(filt), }
    response = requests.get(files_endpt, params=params)

    res = response.json()

    return res['data']['hits'][0]['id']

def get_filename(dataset):
    if dataset == 'brac':
        from conf.brac import settings
        for slide_id, _, _ in settings.file_list():
            yield os.path.basename(slide_id)

def write_single_file(filename, save_dir='/data/smb/syh/WSI_cls/TCGA_BRCA/img'):
    uuid = get_uuid(filename)
    save_path = os.path.join(save_dir, filename)
    data_endpt = "https://api.gdc.cancer.gov/data/{}".format(uuid)
    os.system('wget -c {url}  -O {filename}'.format(url=data_endpt, filename=save_path))

def get_args_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--dataset', required=True, default=None)

    return parser.parse_args()


if '__main__' == __name__:

    args = get_args_parser()
    pool = multiprocessing.Pool(processes=100)
    pool.map(write_single_file, get_filename(args.dataset))
