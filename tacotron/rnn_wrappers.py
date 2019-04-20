# Copyright (c) 2017 Keith Ito
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# ==============================================================================
# Copyright (c) 2018, Yamagishi Laboratory, National Institute of Informatics
# Author: Yusuke Yasuda (yasuda@nii.ac.jp)
# All rights reserved.
# ==============================================================================
""" RNNWrappers.
Modified from keithito's implementation.
Reference: https://github.com/keithito/tacotron/blob/master/models/rnn_wrappers.py
"""

import tensorflow as tf
from tensorflow.contrib.rnn import GRUCell, RNNCell
from tensorflow.contrib.seq2seq import AttentionWrapper
from typing import Tuple
from functools import reduce
from tacotron.modules import PreNet


class DecoderPreNetWrapper(RNNCell):

    def __init__(self, cell: RNNCell, prenets: Tuple[PreNet]):
        super(DecoderPreNetWrapper, self).__init__()
        self._cell = cell
        self.prenets = prenets

    @property
    def state_size(self):
        return self._cell.state_size

    @property
    def output_size(self):
        return self._cell.output_size

    def zero_state(self, batch_size, dtype):
        return self._cell.zero_state(batch_size, dtype)

    def compute_output_shape(self, input_shape):
        return tf.TensorShape([input_shape[0], input_shape[1], self.output_size])

    def call(self, inputs, state):
        prenet_output = reduce(lambda acc, pn: pn(acc), self.prenets, inputs)
        return self._cell(prenet_output, state)


class ConcatOutputAndAttentionWrapper(RNNCell):

    def __init__(self, cell):
        super(ConcatOutputAndAttentionWrapper, self).__init__()
        self._cell = cell

    @property
    def state_size(self):
        return self._cell.state_size

    @property
    def output_size(self):
        return self._cell.output_size + self._cell.state_size.attention

    def zero_state(self, batch_size, dtype):
        return self._cell.zero_state(batch_size, dtype)

    def compute_output_shape(self, input_shape):
        return tf.TensorShape([input_shape[0], input_shape[1], self.output_size])

    def call(self, inputs, state):
        output, res_state = self._cell(inputs, state)
        return tf.concat([output, res_state.attention], axis=-1), res_state


class OutputAndStopTokenWrapper(RNNCell):

    def __init__(self, cell, out_units):
        super(OutputAndStopTokenWrapper, self).__init__()
        self._out_units = out_units
        self._cell = cell
        self.out_projection = tf.layers.Dense(out_units)
        self.stop_token_projectioon = tf.layers.Dense(1)

    @property
    def state_size(self):
        return self._cell.state_size

    @property
    def output_size(self):
        return (self._out_units, 1)

    def zero_state(self, batch_size, dtype):
        return self._cell.zero_state(batch_size, dtype)

    def compute_output_shape(self, input_shape):
        return tf.TensorShape([input_shape[0], input_shape[1], self.output_size])

    def call(self, inputs, state):
        output, res_state = self._cell(inputs, state)
        mel_output = self.out_projection(output)
        stop_token = self.stop_token_projectioon(output)
        return (mel_output, stop_token), res_state


class AttentionRNN(RNNCell):

    def __init__(self, cell, prenets: Tuple[PreNet],
                 attention_mechanism,
                 trainable=True, name=None, **kwargs):
        super(AttentionRNN, self).__init__(name=name, trainable=trainable, **kwargs)
        attention_cell = AttentionWrapper(
            DecoderPreNetWrapper(cell, prenets),
            attention_mechanism,
            cell_input_fn=(lambda inputs, attention: inputs),  # Disable concatenation of inputs and alignment
            alignment_history=True,
            output_attention=False)
        concat_cell = ConcatOutputAndAttentionWrapper(attention_cell)
        self._cell = concat_cell

    @property
    def state_size(self):
        return self._cell.state_size

    @property
    def output_size(self):
        return self._cell.output_size

    def zero_state(self, batch_size, dtype):
        return self._cell.zero_state(batch_size, dtype)

    def compute_output_shape(self, input_shape):
        return tf.TensorShape([input_shape[0], input_shape[1], self.output_size])

    def call(self, inputs, state):
        return self._cell(inputs, state)
