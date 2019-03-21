"""
    def forward(self, minibatch):
        minibatch = minibatch.permute(0,2,1)
        keys = self.key_layer(minibatch)
        queries = self.query_layer(minibatch)
        values = self.value_layer(minibatch)
        logits = torch.bmm(queries, keys.transpose(2,1))
        mask = logits.data.new(logits.size(1), logits.size(2)).fill_(1).byte()
        mask = torch.triu(mask, 1)
        mask = mask.unsqueeze(0).expand_as(logits)
        logits.data.masked_fill_(mask, float('-inf'))
        probs = F.softmax(logits / self.sqrt_k, dim=2)
        read = torch.bmm(probs, values)
        return torch.cat([minibatch, read], dim=2).permute(0,2,1)
"""
import math

import keras.backend as K
import numpy as np
from keras import Input, Model
from keras.datasets import imdb
from keras.layers import Dense, Embedding, Flatten, Lambda
from keras.layers import LSTM
from keras.layers import Layer, Softmax
from keras.preprocessing import sequence

max_features = 20000
# cut texts after this number of words (among top max_features most common words)
maxlen = 80
batch_size = 32


class AttentionBlock(Layer):

    def __init__(self, dims, k_size, v_size, seq_len=None, **kwargs):
        self.k_size = k_size
        self.seq_len = seq_len
        self.v_size = v_size
        self.dims = dims
        self.key_w = None
        self.query_w = None
        self.value_w = None
        self.sqrt_k = math.sqrt(k_size)
        super(AttentionBlock, self).__init__(**kwargs)

    def build(self, input_shape):
        self.key_w = self.add_weight(shape=(self.dims, self.k_size),
                                     name='key_layer',
                                     initializer='glorot_uniform')
        self.query_w = self.add_weight(shape=(self.dims, self.k_size),
                                       name='query_layer',
                                       initializer='glorot_uniform')
        self.value_w = self.add_weight(shape=(self.dims, self.v_size),
                                       name='value_layer',
                                       initializer='glorot_uniform')

    def call(self, inputs, **kwargs):
        keys = K.dot(inputs, self.key_w)
        queries = K.dot(inputs, self.query_w)
        values = K.dot(inputs, self.value_w)
        logits = K.batch_dot(queries, K.permute_dimensions(keys, (0, 2, 1)))
        # logits.data.masked_fill_(mask, float('-inf'))
        mask = Lambda(lambda uu: K.ones_like(uu) * np.triu((-np.inf) * np.ones(uu.shape.as_list()[1:]), k=1))(logits)
        logits = mask + logits
        # logits = logits * (1 - (1 - mask) * (-1000))
        # logits = Lambda(lambda uu: tf.scatter_update(uu, tf.where(mask), -np.inf))(logits)
        # logits = Lambda(lambda uu: uu, mask=mask)(logits)
        probs = Softmax(axis=2)(logits / self.sqrt_k)
        read = K.batch_dot(probs, values)
        output = K.concatenate([inputs, read])
        return output

    def compute_output_shape(self, input_shape):
        output_shape = list(input_shape)
        output_shape[-1] += self.v_size
        return tuple(output_shape)


print('Loading data...')
(x_train, y_train), (x_test, y_test) = imdb.load_data(num_words=max_features)
print(len(x_train), 'train sequences')
print(len(x_test), 'test sequences')

print('Pad sequences (samples x time)')
x_train = sequence.pad_sequences(x_train, maxlen=maxlen)
x_test = sequence.pad_sequences(x_test, maxlen=maxlen)
print('x_train shape:', x_train.shape)
print('x_test shape:', x_test.shape)

print('Build model...')
i = Input(shape=(80,))
x = Embedding(max_features, 128)(i)
x = LSTM(8, dropout=0.2, recurrent_dropout=0.2, return_sequences=True)(x)
x = AttentionBlock(8, 8, 8)(x)
x = Flatten()(x)
x = Dense(1, activation='sigmoid')(x)
model = Model(inputs=[i], outputs=[x])

# try using different optimizers and different optimizer configs
model.compile(loss='binary_crossentropy',
              optimizer='adam',
              metrics=['accuracy'])

print('Train...')
print(x_train.shape)
print(y_train.shape)
model.fit(x_train, y_train,
          batch_size=batch_size,
          epochs=15)
score, acc = model.evaluate(x_test, y_test,
                            batch_size=batch_size)
print('Test score:', score)
print('Test accuracy:', acc)
