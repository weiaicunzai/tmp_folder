
import openslide
import numpy as np
import cv2
import openslide
import os
import sys
import csv
sys.path.append(os.getcwd())




def vis_mask(wsi_path, mask_path, seg_level):
    wsi = openslide.OpenSlide(wsi_path)
    img = wsi.read_region((0,0), seg_level, wsi.level_dimensions[seg_level]).convert('RGB')
    img = np.array(img)

    mask = cv2.imread(mask_path, -1)
    print(img.shape, mask.shape)

    img = cv2.resize(img, mask.shape[::-1])

    mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

    # img[mask>0] =
    print(img.shape, mask.shape)
    res = cv2.addWeighted(img, 0.7, mask, 0.3, 0)

    return res

def get_filenames(settings):

    csv_path = settings.file_list_csv
    with open(csv_path, newline='') as csvfile:
        spamreader = csv.DictReader(csvfile)
        for row in spamreader:
            # if row['slide_id'] != 'TCGA-BH-A2L8-01Z-00-DX1.ACA51CA9-3C38-48A6-B4A9-C12FFAB9AB56.svs':
            #     continue
            yield row['slide_id'], row['label']

def read_img(wsi_path):

    wsi = openslide.OpenSlide(wsi_path)
    # level = 0
    # dims = None
    # count = 0
    for l, d in enumerate(wsi.level_dimensions):
            level = l
            dims = d
            if level == 4:
            # if max(d) < 10000:
                break

    print('read img from wsi {} at level {} dim {}'.format(wsi_path, level, dims))
    img = wsi.read_region((0,0), l, dims).convert('RGB')


    return img


if __name__ == '__main__':

    # wsi_path = '/data/yunpan/syh/PycharmProjects/CGC-Net/data_baiyu/CAMELYON16/training/normal/normal_045.tif'
    # mask_path = '/data/yunpan/syh/PycharmProjects/CGC-Net/data_baiyu/CAMELYON16/training_mask/normal/normal_045.png'

    # out = vis_mask(wsi_path, mask_path, 6)

    # cv2.imwrite('test.jpg', out)
    from conf.camlon16 import settings
    for idx, (filename, label) in enumerate(get_filenames(settings)):
        # print(filename)
        # if filename == 'normal_043'
        # print(filename)
        if 'normal_043' not in filename:
            continue
        print(filename)
        wsi_path = os.path.join(settings.wsi_dir, filename)
        img = read_img(wsi_path)
        print(img)
        img.save('tmp/idx{}_label_{}.jpg'.format(filename, label))
        # break







# def get_

# def level_0_magnification(slide):
#     if 'aperio.AppMag' in slide.properties.keys():
#         level_0_magnification = int(slide.properties['aperio.AppMag'])
#     elif 'openslide.mpp-x' in slide.properties.keys():
#         level_0_magnification = 40 if int(float(slide.properties['openslide.mpp-x']) * 10) == 2 else 20
#     else:
#         level_0_magnification = 40

#     return level_0_magnification

# path = '/data/yunpan/syh/WSI_cls/camelyon16/testing/images/test_007.tif'

# s = openslide.OpenSlide(path)
# # print(s.detect_format(path))
# print(s.level_count)
# print('dimensions', s.dimensions)
# print('level_dimensions', s.level_dimensions)
# print('level_downsamples', s.level_downsamples)
# print('color_profile', s.color_profile)
# print('get_best_level_for_downsample', s.get_best_level_for_downsample(2))
# # print('')
# level_dim = s.level_dimensions

# mag = level_0_magnification(s)
# if mag == 40:
#     layer = 1
# # layer = 1
# img = s.read_region((3000 + 1024 * 2** 5, 3000 + 1024 * 2 ** 5), 5, (1024, 1024))

# s.read_region()
#print(img.shape)
# print(img.size)
# img.convert('RGB').save('test2.jpg')
# print('level_count', s.level_count)
# print('tile_count', s.tile_count)
# print('level_tiles', s.level_tiles)
#print('properties', s.properties)
#print(type(s.properties))
# print()
# for key, value in s.properties.items():
    # print(key, value)

# print(s.properties['openslide.objective-power'])

# print(openslide.detect_format(path))

#print(s.PROPERTY_NAME_OBJECTIVE_POWER)
# print(s.properties.get("openslide.objective-power"))
# print(level_0_magnification(s))

# levels_dim = s.level_dimensions[0]
# x, y = s.level_dimensions[0]
# patch_size = (256, 256)
# #patch_size = (1024, 1024)
# print(levels_dim, patch_size)

# level = 6
# level9 = s.level_dimensions[level]

#comare
# level_dim = s.level_dimensions[level]
# img = s.read_region((0, 0), level,  level_dim).convert('RGB')
# img.save('tmp/img.jpg')



# downsample = int(s.level_downsamples[level])
# print(s.level_dimensions[0])
# for r_idx in range(0, y, patch_size[0] * downsample):
#     for c_idx in range(0, x, patch_size[1] * downsample):
#         # print(r_idx, c_idx)
#         img = s.read_region((c_idx, r_idx), level, patch_size).convert('RGB')
#         # img.save('tmp/img_{}_{}.jpg'.format(c_idx, r_idx))
#         img.save('tmp/img_{}_{}.jpg'.format(r_idx, c_idx))
