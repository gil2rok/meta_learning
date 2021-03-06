import os

import tensorflow as tf
import numpy as np
import tensorflow_addons as tfa

import settings
from models.maml.maml import ModelAgnosticMetaLearningModel
from utils import combine_first_two_axes


class MAMLGAN(ModelAgnosticMetaLearningModel):
    def __init__(self, gan, latent_dim, generated_image_shape, epsilon=0.0, *args, **kwargs):
        super(MAMLGAN, self).__init__(*args, **kwargs)
        self.gan = gan
        self.latent_dim = latent_dim
        self.generated_image_shape = generated_image_shape
        self.tri_mask = np.ones(self.n ** 2, dtype=np.bool).reshape(self.n, self.n)
        self.tri_mask[np.diag_indices(self.n)] = False
        self.num_epsilon_ignore = 0
        self.epsilon = epsilon

    def get_network_name(self):
        return self.model.name

    def get_parse_function(self):
        return self.gan.parser.get_parse_fn()

    def visualize_meta_learning_task(self, shape, num_tasks_to_visualize=1, checkpoint=0):
        import matplotlib.pyplot as plt

        dataset = self.get_train_dataset()
        for item in dataset.repeat(-1).take(num_tasks_to_visualize):
            fig, axes = plt.subplots(self.k_ml + self.k_val_ml, self.n)
            for i in range(len(axes)):
                for j in range(len(axes[i])):
                    axes[i][j].axis('off')

            fig.set_figwidth(self.n)
            fig.set_figheight(self.k_ml + self.k_val_ml)

            (train_ds, val_ds), (_, _) = item
            # Get the first meta batch
            train_ds = train_ds[0, ...]
            val_ds = val_ds[0, ...]
            if shape[2] == 1:
                train_ds = train_ds[..., 0]
                val_ds = val_ds[..., 0]

            for n in range(self.n):
                for k in range(self.k_ml):
                    axes[k, n].imshow(train_ds[n, k, ...])

                for k in range(self.k_val_ml):
                    axes[k + self.k_ml, n].imshow(val_ds[n, k, ...])

            plt.show()

        # for seed in (30445933, 22258032, 66161140, 97465797, 66869316, 17408863):
        # for seed in (22258032, ):
        #    print(seed)
        #    vectors = tf.random.normal((1, self.latent_dim), seed=seed)
        #    images = self.gan.generator(vectors)
        #    plt.imshow(images[0, ..., -1], cmap='gray')
        #    # plt.show()
        #    plt.savefig(
        #        os.path.join(settings.PROJECT_ROOT_ADDRESS, f'plots/lasium_paper/gan_images/{checkpoint}_4')
        #    )

    def squared_dist(self, m):
        expanded_a = tf.expand_dims(m, 1)
        expanded_b = tf.expand_dims(m, 0)
        distances = tf.reduce_sum(tf.math.squared_difference(expanded_a, expanded_b), 2)
        return distances

    def generate_all_vectors_p1(self):
        while True:
            class_vectors = tf.random.normal((self.n, self.latent_dim))
            dist = self.squared_dist(class_vectors)
            elements = tf.boolean_mask(dist, self.tri_mask)
            if tf.reduce_min(elements) > self.epsilon:
                break
            else:
                self.num_epsilon_ignore += 1

        # class_vectors = class_vectors / tf.reshape(tf.norm(class_vectors, axis=1), (class_vectors.shape[0], 1))
        vectors = list()

        vectors.append(class_vectors)
        for i in range(self.k_ml + self.k_val_ml - 1):
            new_vectors = class_vectors
            noise = tf.random.normal(shape=class_vectors.shape, mean=0, stddev=0.5)
            new_vectors += noise
            # new_vectors = new_vectors / tf.reshape(tf.norm(new_vectors, axis=1), (new_vectors.shape[0], 1))
            vectors.append(new_vectors)

        return vectors

    def generate_all_vectors_p2(self):
        class_vectors = tf.random.normal((self.n, self.latent_dim))
        # class_vectors = class_vectors / tf.reshape(tf.norm(class_vectors, axis=1), (class_vectors.shape[0], 1))
        vectors = list()
        vectors.append(class_vectors)
        for i in range(self.k_ml + self.k_val_ml - 1):
            new_vectors = class_vectors
            noise = tf.random.normal(shape=class_vectors.shape, mean=0, stddev=1.0)
            # noise = noise / tf.reshape(tf.norm(noise, axis=1), (noise.shape[0], 1))
            new_vectors = new_vectors + (noise - new_vectors) * 0.2

            vectors.append(new_vectors)
        return vectors

    def generate_all_vectors_p3(self):
        z = tf.random.normal((self.n, self.latent_dim))

        vectors = list()
        vectors.append(z)

        for i in range(self.k_ml + self.k_val_ml - 1):
            if (i + 1) % 5 == 0:
                new_z = z + tf.random.normal(shape=z.shape, mean=0, stddev=1.0)
                vectors.append(new_z)
            else:
                new_z = tf.stack(
                    [
                        z[0, ...] + (z[(i + 1) % self.n, ...] - z[0, ...]) * 0.6,
                        z[1, ...] + (z[(i + 2) % self.n, ...] - z[1, ...]) * 0.6,
                        z[2, ...] + (z[(i + 3) % self.n, ...] - z[2, ...]) * 0.6,
                        z[3, ...] + (z[(i + 4) % self.n, ...] - z[3, ...]) * 0.6,
                        z[4, ...] + (z[(i + 0) % self.n, ...] - z[4, ...]) * 0.6,
                    ],
                    axis=0
                )
                vectors.append(new_z)

        return vectors

    def generate_all_vectors(self):
        return self.generate_all_vectors_p1()

    @tf.function
    def get_images_from_vectors(self, vectors):
        return self.gan.generator(vectors)

    def get_train_dataset(self):
        train_labels = tf.repeat(tf.range(self.n), self.k_ml)
        train_labels = tf.one_hot(train_labels, depth=self.n)
        train_labels = tf.stack([train_labels] * self.meta_batch_size)
        val_labels = tf.repeat(tf.range(self.n), self.k_val_ml)
        val_labels = tf.one_hot(val_labels, depth=self.n)
        val_labels = tf.stack([val_labels] * self.meta_batch_size)

        # print('debug\n\n\n')
        # print(train_labels)
        # print(val_labels)
        # print('debug\n\n\n')

        train_indices = [i // self.k_ml + i % self.k_ml * self.n for i in range(self.n * self.k_ml)]
        val_indices = [i // self.k_val_ml + i % self.k_val_ml * self.n for i in range(self.n * self.k_val_ml)]

        def get_task():
            meta_batch_vectors = list()

            for meta_batch in range(self.meta_batch_size):
                vectors = self.generate_all_vectors()
                vectors = tf.reshape(tf.stack(vectors, axis=0), (-1, self.latent_dim))
                meta_batch_vectors.append(vectors)

            meta_batch_vectors = tf.stack(meta_batch_vectors)
            meta_batch_vectors = combine_first_two_axes(meta_batch_vectors)
            images = self.get_images_from_vectors(meta_batch_vectors)
            images = tf.image.resize(images, self.generated_image_shape[:2])
            images = tf.reshape(
                images,
                (self.meta_batch_size, self.n * (self.k_ml + self.k_val_ml), *self.generated_image_shape)
            )

            train_ds = images[:, :self.n * self.k_ml, ...]
            train_ds = tf.gather(train_ds, train_indices, axis=1)
            train_ds = tf.reshape(train_ds, (self.meta_batch_size, self.n, self.k_ml, *self.generated_image_shape))

            val_ds = images[:, self.n * self.k_ml:, ...]
            val_ds = combine_first_two_axes(val_ds)
            # Process val if needed
            val_imgs = list()
            for i in range(val_ds.shape[0]):
                val_image = val_ds[i, ...]
                tx = tf.random.uniform((), -5, 5, dtype=tf.int32)
                ty = tf.random.uniform((), -15, 15, dtype=tf.int32)
                transforms = [1, 0, -tx, 0, 1, -ty, 0, 0]
                val_image = tfa.image.transform(val_image, transforms, 'NEAREST')

                val_image = tf.image.random_crop(val_image, size=(64, 64, 3))
                val_imgs.append(val_image)

            val_ds = tf.stack(val_imgs, axis=0)
            val_ds = tf.image.resize(val_ds, size=(84, 84))
            # process stops here

            val_ds = tf.reshape(val_ds, (self.meta_batch_size, self.n * self.k_val_ml, *self.generated_image_shape))
            val_ds = tf.gather(val_ds, val_indices, axis=1)
            val_ds = tf.reshape(val_ds, (self.meta_batch_size, self.n, self.k_val_ml, *self.generated_image_shape))

            yield (train_ds, val_ds), (train_labels, val_labels)

        dataset = tf.data.Dataset.from_generator(
            get_task,
            output_types=((tf.float32, tf.float32), (tf.float32, tf.float32))
        )
        setattr(dataset, 'steps_per_epoch', tf.data.experimental.cardinality(dataset))
        return dataset
