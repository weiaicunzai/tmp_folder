import argparse
import os
import io
import csv
import struct

import torch
# from torch.utils.data import Dataset, IterableDataset, DataLoader
from torch.utils.data import Dataset, DataLoader
import openslide
import time
import multiprocessing as mp

from multiprocessing import Process, Queue, Pool


import lmdb

import os
import sys
import struct
sys.path.append(os.getcwd())
import torch
from torchvision import transforms
from PIL import Image
import  lmdb
import json
# from preprocess.utils import get_vit256
from preprocess.resnet_custom import resnet50_baseline


def worker(json_path):
    json_data = json.load(open(json_path, 'r'))
    coords = json_data['coords'][0]

    base_name = json_data['filename']
    keys = []
    for coord in coords:
        # (x, y), level, (patch_size_x, patch_size_y) = coord

        # assert isinstance(x, int)
        # assert isinstance(y, int)
        # assert isinstance(level, int)
        # assert isinstance(patch_size_x, int)
        # assert isinstance(patch_size_y, int)

        # patch_id = '{basename}_{x}_{y}_{level}_{patch_size_x}_{patch_size_y}'.format(
        #     basename=base_name,
        #     x=x,
        #     y=y,
        #     level=level,
        #     patch_size_x=patch_size_x,
        #     patch_size_y=patch_size_y)

        # keys.append(patch_id)
        keys.append([base_name, coord])

    return keys

def get_wsi(path):
    wsi = openslide.open_slide(path)
    basename = os.path.basename(path)
    return {basename : wsi}

class PatchLMDB(Dataset):
    def __init__(self, settings, trans, cont) -> None:
        print('loading keys .....')
        self.keys = self.load_keys(settings)
        # if cont:
            # self.keys = self.filter_keys(self.keys, settings.feat_dir)

        self.wsis = self.load_wsis(settings)
        # num_keys = self.env.stat()['entries']
        # assert num_keys == len(self.keys)
        print('done, total {} number of keys'.format(len(self.keys)))
        self.trans = trans
        self.patch_size = settings.patch_size

        # self.patch_env = lmdb.open(settings.patch_dir, readonly=True, lock=False)
        # self.feat_env = lmdb.open(settings.feat_dir, readonly=True, lock=False)

    # def load_wsis(self, settings):
    #     wsis = {}

    #     csv_path = settings.file_list_csv
    #     file_path = []
    #     with open(csv_path, 'r') as csv_file:
    #         for row in csv.DictReader(csv_file):
    #             slide_id = row['slide_id']
    #             path = os.path.join(settings.wsi_dir, slide_id)
    #             file_path.append(path)
    #             # wsis[slide_id] = openslide.open_slide(path)
    #     pool = Pool(processes=mp.cpu_count())
    #     keys = pool.map(get_wsi, file_path)
    #     for key in keys:
    #         wsis.update(key)
    def filter_keys(self, keys, feat_path):
        env = lmdb.open(feat_path, readonly=True, lock=False)
        print(feat_path)
        with env.begin(write=False) as txn:
            cursor = txn.cursor()
            for key in keys:

                base_name, coord = key
                (x, y), level, (patch_size_x, patch_size_y) = coord

                assert isinstance(x, int)
                assert isinstance(y, int)
                assert isinstance(level, int)
                assert isinstance(patch_size_x, int)
                assert isinstance(patch_size_y, int)

                patch_id = '{basename}_{x}_{y}_{level}_{patch_size_x}_{patch_size_y}'.format(
                    basename=base_name,
                    x=x,
                    y=y,
                    level=level,
                    patch_size_x=patch_size_x,
                    patch_size_y=patch_size_y)

                print(cursor.set_key(patch_id.encode()))
                # key = next(cursor.iternext(values=False))
                # key = next(cursor.iternext())
                print(key, 'ccc')
                key = cursor.first()
                print(key)
                # key = key[0]
                # print(cursor.set_key(key[0].encode()))
                import sys; sys.exit()



    #     return wsis
    def load_wsis(self, settings):
        wsis = {}

        csv_path = settings.file_list_csv
        # count = 0
        with open(csv_path, 'r') as csv_file:
            for row in csv.DictReader(csv_file):
                # count += 1
                slide_id = row['slide_id']
                path = os.path.join(settings.wsi_dir, slide_id)
                print(path)
                wsis[slide_id] = openslide.open_slide(path)
                # if count > 10:
                    # break

        return wsis

    def load_keys(self, settings):
        csv_path = settings.file_list_csv
        json_dir = settings.json_dir
        json_names = []
        with open(csv_path, 'r') as csv_file:
            for row in csv.DictReader(csv_file):
                slide_id = row['slide_id']
                json_name = os.path.splitext(slide_id)[0] + '.json'
                json_path = os.path.join(json_dir, json_name)
                json_names.append(json_path)

        # json_names = json_names[:10]
        t1 = time.time()
        pool = Pool(processes=mp.cpu_count())
        keys = pool.map(worker, json_names)
        print('using {:4f}s to load'.format(time.time() - t1))

        res = []
        for k in keys:
            res.extend(k)

        return res

    def __len__(self):
        return len(self.keys)

    def __getitem__(self, idx):
        # patch_id = self.keys[idx]
        base_name, coord = self.keys[idx]
        wsi = self.wsis[base_name]
        img = wsi.read_region(*coord).convert('RGB')


        # with self.env.begin(write=False) as txn:
        #     # print(patch_id)
        #     img_stream = txn.get(patch_id.encode())
        #     img = Image.open(io.BytesIO(img_stream))

        if self.trans is not None:
            img = self.trans(img)

        (x, y), level, (patch_size_x, patch_size_y) = coord

        assert isinstance(x, int)
        assert isinstance(y, int)
        assert isinstance(level, int)
        assert isinstance(patch_size_x, int)
        assert isinstance(patch_size_y, int)

        patch_id = '{basename}_{x}_{y}_{level}_{patch_size_x}_{patch_size_y}'.format(
            basename=base_name,
            x=x,
            y=y,
            level=level,
            patch_size_x=patch_size_x,
            patch_size_y=patch_size_y)

        return {'img':img, 'patch_id':patch_id}


# def eval_transforms(patch_size):
# 	"""
# 	"""
# 	mean, std = (0.5, 0.5, 0.5), (0.5, 0.5, 0.5)
# 	eval_t = transforms.Compose([
#             transforms.Resize((patch_size, patch_size)),
#             transforms.ToTensor(),
#             transforms.Normalize(mean = mean, std = std)
#         ])
# 	return eval_t

def eval_transforms(patch_size, pretrained=False):
	if pretrained:
		mean = (0.485, 0.456, 0.406)
		std = (0.229, 0.224, 0.225)

	else:
		mean = (0.5,0.5,0.5)
		std = (0.5,0.5,0.5)

	trnsfrms_val = transforms.Compose(
					[
                     transforms.Resize((patch_size, patch_size)),
					 transforms.ToTensor(),
					 transforms.Normalize(mean = mean, std = std)
					]
				)

	return trnsfrms_val

def get_args_parser():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--dataset', required=True, default=None)
    # parser.add_argument('--ckpt', required=True, default=None)
    parser.add_argument('--cont', action='store_true', help='enable')

    return parser.parse_args()

def writer_process(settings, q, num_patches):

    # env = lmdb.open(settings.patch_dir, readonly=True, lock=False)
    # with env.begin() as txn:
        # num_patches = txn.stat()['entries']

    count = 0
    t1 = time.time()

    db_size = 1 << 42
    env = lmdb.open(settings.feat_dir, map_size=db_size)


    with env.begin(write=True) as txn:
        while True:
            record = q.get()

            for patch_id, feat in zip(*record):
                # struct use 2 times less mem storage than torch.save
                # and 3 times faster to decode (struct.unpack+torch.tensor)
                # than torch.load from byte string

                feat = struct.pack('1024f', *feat.tolist())
                txn.put(patch_id.encode(), feat)
                count += 1

                if count % 1000 == 0:
                    print('processed {} patches, avg time {:04f}'.format(
                        count,
                        (time.time() - t1) / count
                    ))

            if count == num_patches:
                break

if __name__ == '__main__':
    args = get_args_parser()
    if args.dataset == 'brac':
        from conf.brac import settings
    elif args.dataset == 'cam16':
        from conf.camlon16 import settings
    elif args.dataset == 'lung':
        from conf.lung import settings
    else:
        raise ValueError('wrong dataset')

    feat_dir = settings.feat_dir
    print(feat_dir)
    if not os.path.exists(feat_dir):
        os.makedirs(feat_dir)

    trans = eval_transforms(settings.patch_size, pretrained=True)
    print(trans)

    dataset = PatchLMDB(settings, trans=trans, cont=args.cont)
    num_patches = len(dataset.keys)
    # dataloader = DataLoader(dataset, num_workers=4, batch_size=256 * 4, pin_memory=True, prefetch_factor=8)
    # dataloader = DataLoader(dataset, num_workers=4, batch_size=256 * 4, pin_memory=True)
    # dataloader = DataLoader(dataset, num_workers=8, batch_size=256 * 4, pin_memory=True, prefetch_factor=8)
    dataloader = DataLoader(dataset, num_workers=8, batch_size=256 * 4, pin_memory=True)

    # model = get_vit256(args.ckpt).cuda()
    model = resnet50_baseline(pretrained=True).cuda()
    if torch.cuda.device_count() > 1:
        model = torch.nn.DataParallel(model)
    model = model.eval()

    q = Queue()

    # since lmdb only allows one process to write at the same time
    # we use another writer process to perfom writing operation
    # when dataloader is reading data.
    writer_proc = Process(target=writer_process, args=(settings, q, num_patches))
    writer_proc.start()

    for data in dataloader:
        img = data['img'].cuda(non_blocking=True)
        print(img.shape)

        with torch.no_grad():
            out = model(img)

        out = out.cpu()
        q.put((data['patch_id'], out))

    writer_proc.join()
    print('done processing...')
