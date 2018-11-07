import os
import argparse
import logging
import time

import numpy as np
from PIL import Image, ImageDraw


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', default='', type=str,
                        help='The filename of image to be completed.')
    parser.add_argument('--mask', default='', type=str,
                        help='The filename of mask, value 255 indicates mask.')
    parser.add_argument('--output', default='output.png', type=str,
                        help='Where to write output.')
    parser.add_argument('--checkpoint_dir', default='', type=str,
                        help='The directory of tensorflow checkpoint.')
    return parser.parse_args()


class ShiftNetInpaintingWorker:

    def __init__(
        self, logger=logging.getLogger(__name__),
        image_height=180, image_width=320,
        checkpoint_dir='model_logs/release_places2_256',
        refine=False
    ):
        self.logger = logger
        self.logger.info("Initializing ..")
        self.refine = refine
        # ng.get_gpus(1)

        self.checkpoint_dir = checkpoint_dir
        self.grid = 8
        # Image size that the model could handle
        self.ph_height = image_height // self.grid * self.grid
        self.ph_width = image_width // self.grid * self.grid * 2
        assert os.path.exists(self.checkpoint_dir)

        self._setup(refine)
        self.logger.info("Initialization done")

    def _setup(self, refine):
        """ Setup the model here"""
        self.model = None

    def _draw_bboxes(self, img, bboxes):
        draw = ImageDraw.Draw(img)
        for i, bbox in enumerate(bboxes):
            (x1, y1), (x2, y2) = bbox
            draw.rectangle(((x1, y1), (x2, y2)), outline="red")
        return img

    def infer(
        self, images, bboxeses, draw_bbox=False
    ):

        start_time = time.time()
        h, w, _ = images[0].shape
        self.logger.info(f"Shape: {images.shape}")

        result_images = []
        for i, (image, bboxes) in enumerate(zip(images, bboxeses)):
            if len(bboxes) == 0:
                result_image = Image.fromarray(
                    image.astype('uint8'))
                result_images.append(result_image)
                self.logger.warning(f"No bboxes in frame {i}, skipped")
                continue
            mask = np.zeros(image.shape)
            (x1, y1), (x2, y2) = bboxes[0]
            mask[y1:y2, x1:x2, :] = [255, 255, 255]
            image_ = image[:h//self.grid*self.grid, :w//self.grid*self.grid, :]
            mask = mask[:h//self.grid*self.grid, :w//self.grid*self.grid, :]

            """ Do the inference here"""
            image_ = np.expand_dims(image_, 0)
            mask = np.expand_dims(mask, 0)
            input_image = np.concatenate([image_, mask], axis=2)
            if self.refine:
                result_np, dump_x1, dump_x2_ro = self.sess.run(
                    [self.output, self.model.x1, self.model.x2_refine_only],
                    feed_dict={self.input_image_ph: input_image})
                dump_img_o = Image.fromarray(
                    result_np[0].astype('uint8')[:, :, ::-1])
                dump_img_x1 = Image.fromarray(
                    ((dump_x1+1)*127.5)[0].astype('uint8'))
                dump_img_x2_ro = Image.fromarray(
                    ((dump_x2_ro+1)*127.5)[0].astype('uint8'))
                dump_img_o.save('debug_o.png')
                dump_img_x1.save('debug_x1.png')
                dump_img_x2_ro.save('debug_x2.png')
            else:
                result_np = self.sess.run(
                    self.output,
                    feed_dict={self.input_image_ph: input_image})
            """ Put the result back to original size and draw bbox if needed"""
            result = image.copy()
            result[
               :h//self.grid*self.grid, :w//self.grid*self.grid, :
            ] = result_np
            result_image = Image.fromarray(
                result.astype('uint8')[:, :, ::-1])
            if draw_bbox:
                self._draw_bboxes(result_image, bboxes)
            result_images.append(result_image)
        self.logger.info(f"Time: {time.time() - start_time}")
        return result_images


def main():
    args = get_args()
    image = np.array(Image.open(args.image).convert("RGB"))
    images = np.array([image/2, image])
    bboxeses = [[(10, 10), (100, 100)], [(20, 30), (40, 200)]]
    shiftnet_worker = ShiftNetInpaintingWorker()
    results = shiftnet_worker.infer(images, bboxeses)
    results[0].save(args.output)
    results[1].save(args.output+'_2.png')


if __name__ == "__main__":
    main()
