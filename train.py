"""
   Trainer for a simplifed version of Baidu DeepSpeech2 model.
"""

import paddle.v2 as paddle
import argparse
import gzip
import sys
from model import deep_speech2
import audio_data_utils

#TODO: add WER metric

parser = argparse.ArgumentParser(
    description='Simplified version of DeepSpeech2 trainer.')
parser.add_argument(
    "--batch_size", default=512, type=int, help="Minibatch size.")
parser.add_argument("--trainer", default=1, type=int, help="Trainer number.")
parser.add_argument(
    "--num_passes", default=20, type=int, help="Training pass number.")
parser.add_argument(
    "--num_conv_layers", default=3, type=int, help="Convolution layer number.")
parser.add_argument(
    "--num_rnn_layers", default=5, type=int, help="RNN layer number.")
parser.add_argument(
    "--rnn_layer_size", default=256, type=int, help="RNN layer cell number.")
parser.add_argument(
    "--use_gpu", default=True, type=bool, help="Use gpu or not.")
parser.add_argument(
    "--use_sortagrad", default=False, type=bool, help="Use sortagrad or not.")
parser.add_argument(
    "--trainer_count", default=8, type=int, help="Trainer number.")
args = parser.parse_args()


def train():
    """
    DeepSpeech2 training.
    """
    # create network config
    dict_size = audio_data_utils.get_vocabulary_size()
    audio_data = paddle.layer.data(
        name="audio_spectrogram",
        height=161,
        width=1000,
        type=paddle.data_type.dense_vector(161000))
    text_data = paddle.layer.data(
        name="transcript_text",
        type=paddle.data_type.integer_value_sequence(dict_size))
    cost, _ = deep_speech2(
        audio_data=audio_data,
        text_data=text_data,
        dict_size=dict_size,
        num_conv_layers=args.num_conv_layers,
        num_rnn_layers=args.num_rnn_layers,
        rnn_size=args.rnn_layer_size)

    # create parameters and optimizer
    parameters = paddle.parameters.create(cost)
    optimizer = paddle.optimizer.Adam(
        learning_rate=5e-4, gradient_clipping_threshold=400)
    trainer = paddle.trainer.SGD(
        cost=cost, parameters=parameters, update_equation=optimizer)
    # create data readers
    feeding = {
        "audio_spectrogram": 0,
        "transcript_text": 1,
    }
    train_batch_reader_with_sortagrad = audio_data_utils.padding_batch_reader(
        paddle.batch(
            audio_data_utils.reader_creator(
                manifest_path="./libri.manifest.train", sort_by_duration=True),
            batch_size=args.batch_size // args.trainer),
        padding=[-1, 1000])
    train_batch_reader_without_sortagrad = audio_data_utils.padding_batch_reader(
        paddle.batch(
            audio_data_utils.reader_creator(
                manifest_path="./libri.manifest.train",
                sort_by_duration=False,
                shuffle=True),
            batch_size=args.batch_size // args.trainer),
        padding=[-1, 1000])
    test_batch_reader = audio_data_utils.padding_batch_reader(
        paddle.batch(
            audio_data_utils.reader_creator(
                manifest_path="./libri.manifest.dev", sort_by_duration=False),
            batch_size=args.batch_size // args.trainer),
        padding=[-1, 1000])

    # create event handler
    def event_handler(event):
        if isinstance(event, paddle.event.EndIteration):
            if event.batch_id % 10 == 0:
                print "/nPass: %d, Batch: %d, TrainCost: %f" % (
                    event.pass_id, event.batch_id, event.cost)
            else:
                sys.stdout.write('.')
                sys.stdout.flush()
        if isinstance(event, paddle.event.EndPass):
            result = trainer.test(reader=test_batch_reader, feeding=feeding)
            print "Pass: %d, TestCost: %s" % (event.pass_id, result.cost)
            with gzip.open("params.tar.gz", 'w') as f:
                parameters.to_tar(f)

    # run train
    # first pass with sortagrad
    if args.use_sortagrad:
        trainer.train(
            reader=train_batch_reader_with_sortagrad,
            event_handler=event_handler,
            num_passes=1,
            feeding=feeding)
        args.num_passes -= 1
    # other passes without sortagrad
    trainer.train(
        reader=train_batch_reader_without_sortagrad,
        event_handler=event_handler,
        num_passes=args.num_passes,
        feeding=feeding)


def main():
    paddle.init(use_gpu=args.use_gpu, trainer_count=args.trainer_count)
    train()


if __name__ == '__main__':
    main()
