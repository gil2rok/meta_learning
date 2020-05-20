from abc import abstractmethod

import tensorflow as tf


class BaseParser(object):
    def __init__(self, shape):
        self.shape = shape

    @abstractmethod
    def get_parse_fn(self):
        pass


class OmniglotParser(BaseParser):
    def get_parse_fn(self):
        @tf.function
        def parse(example_address):
            image = tf.image.decode_png(tf.io.read_file(example_address))
            image = tf.reshape(tf.image.resize(image, self.shape[:2]), self.shape)
            image = tf.cast(image, tf.float32)

            return image / 255.

        return parse


class CelebAParser(BaseParser):
    def get_parse_fn(self):
        @tf.function
        def parse(example_address):
            image = tf.image.decode_png(tf.io.read_file(example_address))
            image = tf.reshape(tf.image.resize(image, self.shape[:2]), self.shape)
            image = tf.cast(image, tf.float32)

            return image / 255.

        return parse


class VoxCelebParser(BaseParser):
    def get_parse_fn(self):
        @tf.function
        def parse_function(example_address):
            audio_track, sample_rate = tf.audio.decode_wav(
                tf.io.read_file(example_address),
                desired_samples=16000,
                desired_channels=1)
            audio_track = tf.cast(audio_track, tf.float32)

            return audio_track

        return parse_function
