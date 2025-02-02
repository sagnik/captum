import glob
import tempfile
from datetime import datetime
from typing import List, cast

import torch
from captum._utils.av import AV
from tests.helpers.basic import BaseTest, assertTensorAlmostEqual
from tests.helpers.basic_models import BasicLinearReLULinear
from torch.utils.data import DataLoader, Dataset

DEFAULT_IDENTIFIER = "default_identifier"


class RangeDataset(Dataset):
    def __init__(self, low, high, num_features):
        self.samples = (
            torch.arange(start=low, end=high, dtype=torch.float)
            .repeat(num_features, 1)
            .transpose(1, 0)
        )

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


class Test(BaseTest):
    def test_exists_without_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            av_0 = torch.randn(64, 16)
            self.assertFalse(AV.exists(tmpdir, "dummy", "layer1.0.conv1"))

            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv1", av_0, "0")
            self.assertTrue(
                AV.exists(
                    tmpdir,
                    "dummy",
                    DEFAULT_IDENTIFIER,
                    "layer1.0.conv1",
                )
            )

    def test_exists_with_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            idf1 = str(int(datetime.now().microsecond))
            idf2 = "idf2"
            av_0 = torch.randn(64, 16)

            self.assertFalse(AV.exists(tmpdir, "dummy", "layer1.0.conv1", idf1))
            self.assertFalse(AV.exists(tmpdir, "dummy", "layer1.0.conv1", idf2))

            AV.save(tmpdir, "dummy", idf1, "layer1.0.conv1", av_0, "0")
            self.assertTrue(AV.exists(tmpdir, "dummy", idf1, "layer1.0.conv1"))
            self.assertFalse(AV.exists(tmpdir, "dummy", idf2, "layer1.0.conv1"))

            AV.save(tmpdir, "dummy", idf2, "layer1.0.conv1", av_0, "0")
            self.assertTrue(AV.exists(tmpdir, "dummy", idf2, "layer1.0.conv1"))

    def test_av_save_two_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            av_0 = torch.randn(64, 16)

            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv1", av_0, "0")
            self.assertTrue(
                AV.exists(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv1")
            )
            self.assertFalse(
                AV.exists(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv2")
            )

            # experimenting with adding to another layer
            av_1 = torch.randn(64, 16)
            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv2", av_1, "0")
            self.assertTrue(
                AV.exists(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv2")
            )

    def test_av_save_multi_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            av_0 = torch.randn(64, 16)
            av_1 = torch.randn(64, 16)
            av_2 = torch.randn(64, 16)

            model_path = AV._assemble_model_dir(tmpdir, "dummy")

            # save first layer
            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv1", av_0, "0")
            self.assertEqual(len(glob.glob(model_path + "*")), 1)

            # add two new layers at once
            AV.save(
                tmpdir,
                "dummy",
                DEFAULT_IDENTIFIER,
                ["layer1.0.conv2", "layer1.1.conv1"],
                [av_1, av_2],
                "0",
            )

            self.assertEqual(len(glob.glob(model_path + "/*/*/*")), 3)

            # overwrite the first saved layer
            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv1", av_0, "0")
            self.assertEqual(len(glob.glob(model_path + "/*/*/*")), 3)

            # save a new version of the first layer
            idf1 = str(int(datetime.now().microsecond))
            self.assertFalse(AV.exists(tmpdir, "dummy", idf1, "layer1.0.conv1"))
            AV.save(tmpdir, "dummy", idf1, "layer1.0.conv1", av_0, "0")

            self.assertTrue(AV.exists(tmpdir, "dummy", idf1, "layer1.0.conv1"))
            self.assertEqual(len(glob.glob(model_path + "/*/*/*")), 4)

    def test_av_save_multiple_batches_per_layer(self) -> None:
        def save_and_assert_batch(layer_path, total_num_batches, batch, n_batch_name):
            # save n-th batch and verify the number of saved batches
            AV.save(
                tmpdir,
                model_id,
                DEFAULT_IDENTIFIER,
                "layer1.0.conv1",
                batch,
                n_batch_name,
            )
            self.assertEqual(
                len(glob.glob("/".join([layer_path, "*.pt"]))),
                total_num_batches,
            )
            self.assertTrue(
                AV.exists(
                    tmpdir, model_id, DEFAULT_IDENTIFIER, "layer1.0.conv1", n_batch_name
                )
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            b0 = torch.randn(64, 16)
            b1 = torch.randn(64, 16)
            b2 = torch.randn(64, 16)

            model_id = "dummy"
            model_path = AV._assemble_model_dir(tmpdir, model_id)

            layer_path = AV._assemble_file_path(
                model_path, DEFAULT_IDENTIFIER, "layer1.0.conv1"
            )

            # save first batch and verify the number of saved batches
            save_and_assert_batch(layer_path, 1, b0, "0")

            # save second batch and verify the number of saved batches
            save_and_assert_batch(layer_path, 2, b1, "1")

            # save third batch and verify the number of saved batches
            save_and_assert_batch(layer_path, 3, b2, "2")

    def test_av_load_multiple_batches_per_layer(self) -> None:
        def save_load_and_assert_batch(
            layer_path, total_num_batches, batch, n_batch_name
        ):
            # save n-th batch and verify the number of saved batches
            AV.save(
                tmpdir,
                model_id,
                DEFAULT_IDENTIFIER,
                "layer1.0.conv1",
                batch,
                n_batch_name,
            )
            loaded_dataset = AV.load(
                tmpdir, model_id, DEFAULT_IDENTIFIER, "layer1.0.conv1", n_batch_name
            )
            self.assertIsNotNone(loaded_dataset)
            assertTensorAlmostEqual(self, next(iter(loaded_dataset)), batch, 0.0)

            loaded_dataset_for_layer = AV.load(
                tmpdir, model_id, DEFAULT_IDENTIFIER, "layer1.0.conv1"
            )
            self.assertEqual(
                loaded_dataset_for_layer.__len__(),
                total_num_batches,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            b0 = torch.randn(64, 16)
            b1 = torch.randn(64, 16)
            b2 = torch.randn(64, 16)

            model_id = "dummy"
            model_path = AV._assemble_model_dir(tmpdir, model_id)

            layer_path = AV._assemble_file_path(
                model_path, DEFAULT_IDENTIFIER, "layer1.0.conv1"
            )

            # save first batch and verify the number of saved batches
            save_load_and_assert_batch(layer_path, 1, b0, "0")

            # save second batch and verify the number of saved batches
            save_load_and_assert_batch(layer_path, 2, b1, "1")

            # save third batch and verify the number of saved batches
            save_load_and_assert_batch(layer_path, 3, b2, "2")

    def test_av_load_non_saved_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset = AV.load(tmpdir, "dummy")
            self.assertIsNone(dataset)

    def test_av_load_one_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            av_0 = torch.randn(64, 16)
            av_1 = torch.randn(36, 16)
            avs = [av_0, av_1]

            # add av_0 to the list of activations
            dataset = AV.load(tmpdir, "dummy")
            self.assertIsNone(dataset)

            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv1", av_0, "0")
            dataset = AV.load(tmpdir, "dummy", identifier=DEFAULT_IDENTIFIER)
            self.assertIsNotNone(dataset)
            for i, av in enumerate(DataLoader(cast(Dataset, dataset))):
                assertTensorAlmostEqual(self, av, avs[i])

            # add av_1 to the list of activations
            dataloader_2 = DataLoader(
                cast(
                    Dataset,
                    AV.load(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv2"),
                )
            )
            self.assertEqual(len(dataloader_2), 0)

            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv2", av_1, "0")
            dataset = AV.load(tmpdir, "dummy", identifier=DEFAULT_IDENTIFIER)
            self.assertIsNotNone(dataset)
            dataloader = DataLoader(cast(Dataset, dataset))
            self.assertEqual(len(dataloader), 2)
            for i, av in enumerate(dataloader):
                assertTensorAlmostEqual(self, av, avs[i])

    def test_av_load_all_identifiers_one_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            av_0 = torch.randn(64, 16)
            av_1 = torch.randn(36, 16)
            av_2 = torch.randn(16, 16)
            av_3 = torch.randn(4, 16)
            avs = [av_1, av_2, av_3]

            idf1, idf2, idf3 = "idf1", "idf2", "idf3"

            AV.save(tmpdir, "dummy", DEFAULT_IDENTIFIER, "layer1.0.conv1", av_0, "0")
            dataloader = DataLoader(
                cast(Dataset, AV.load(tmpdir, "dummy", identifier=DEFAULT_IDENTIFIER))
            )
            self.assertEqual(len(dataloader), 1)

            # add activations for another layer
            AV.save(tmpdir, "dummy", idf1, "layer1.0.conv2", av_1, "0")
            AV.save(tmpdir, "dummy", idf2, "layer1.0.conv2", av_2, "0")
            AV.save(tmpdir, "dummy", idf3, "layer1.0.conv2", av_3, "0")
            dataloader_layer = DataLoader(
                cast(
                    Dataset,
                    AV.load(
                        tmpdir,
                        "dummy",
                        layer="layer1.0.conv2",
                    ),
                )
            )

            self.assertEqual(len(dataloader_layer), 3)
            for i, av in enumerate(dataloader_layer):
                assertTensorAlmostEqual(self, av, avs[i])

            dataloader = DataLoader(cast(Dataset, AV.load(tmpdir, "dummy")))
            self.assertEqual(len(dataloader), 4)

    def test_av_load_all_layers_one_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            av_01 = torch.randn(36, 16)
            av_02 = torch.randn(16, 16)
            av_03 = torch.randn(4, 16)
            avs_0 = [av_01, av_02, av_03]

            av_11 = torch.randn(36, 16)
            av_12 = torch.randn(16, 16)
            av_13 = torch.randn(4, 16)
            avs_1 = [av_11, av_12, av_13]

            idf1, idf2 = "idf1", "idf2"

            AV.save(
                tmpdir,
                "dummy",
                idf1,
                ["layer1.0.conv1", "layer1.0.conv2", "layer1.1.conv1"],
                avs_0,
                "0",
            )
            dataloader = DataLoader(cast(Dataset, AV.load(tmpdir, "dummy")))
            self.assertEqual(len(dataloader), 3)

            AV.save(
                tmpdir,
                "dummy",
                idf2,
                ["layer1.0.conv1", "layer1.0.conv2", "layer1.1.conv1"],
                avs_1,
                "0",
            )
            dataloader = DataLoader(cast(Dataset, AV.load(tmpdir, "dummy")))
            self.assertEqual(len(dataloader), 6)

            # check activations for idf1
            dataloader_layer = DataLoader(
                cast(Dataset, AV.load(tmpdir, "dummy", identifier=idf1))
            )
            self.assertEqual(len(dataloader_layer), 3)

            for i, av in enumerate(dataloader_layer):
                assertTensorAlmostEqual(self, av, avs_0[i])

            # check activations for idf2
            dataloader_layer = DataLoader(
                cast(Dataset, AV.load(tmpdir, "dummy", identifier=idf2))
            )
            self.assertEqual(len(dataloader_layer), 3)
            for i, av in enumerate(dataloader_layer):
                assertTensorAlmostEqual(self, av, avs_1[i])

    def test_av_sort_files(self) -> None:
        files = ["resnet50-cifar-3000", "resnet50-cifar-1000", "resnet50-cifar-2000"]
        exp_files = [
            "resnet50-cifar-1000",
            "resnet50-cifar-2000",
            "resnet50-cifar-3000",
        ]
        files = AV.sort_files(files)

        self.assertEqual(files, exp_files)

        files = ["resnet50-cifar-0900", "resnet50-cifar-0000", "resnet50-cifar-1000"]
        exp_files = [
            "resnet50-cifar-0000",
            "resnet50-cifar-0900",
            "resnet50-cifar-1000",
        ]
        files = AV.sort_files(files)
        self.assertEqual(files, exp_files)

        files = ["resnet50-cifar-100", "resnet50-cifar-90", "resnet50-cifar-3000"]
        exp_files = [
            "resnet50-cifar-90",
            "resnet50-cifar-100",
            "resnet50-cifar-3000",
        ]
        files = AV.sort_files(files)
        self.assertEqual(files, exp_files)

        files = [
            "av/pretrained-net-0/fc1-src10-710935.pt",
            "av/pretrained-net-0/fc1-src11-755317.pt",
            "av/pretrained-net-0/fc3-src2-655646.pt",
            "av/pretrained-net-0/fc1-src9-952381.pt",
            "av/pretrained-net-0/conv2-src7-811286.pt",
            "av/pretrained-net-0/fc1-src10-176141.pt",
            "av/pretrained-net-0/conv11-src9-384927.pt",
        ]
        exp_files = [
            "av/pretrained-net-0/conv2-src7-811286.pt",
            "av/pretrained-net-0/conv11-src9-384927.pt",
            "av/pretrained-net-0/fc1-src9-952381.pt",
            "av/pretrained-net-0/fc1-src10-176141.pt",
            "av/pretrained-net-0/fc1-src10-710935.pt",
            "av/pretrained-net-0/fc1-src11-755317.pt",
            "av/pretrained-net-0/fc3-src2-655646.pt",
        ]
        files = AV.sort_files(files)
        self.assertEqual(files, exp_files)

    def test_generate_activation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            num_features = 4
            low, high = 0, 16
            mymodel = BasicLinearReLULinear(num_features)
            mydata = RangeDataset(low, high, num_features)
            layers: List[str] = []
            for name, _module in mymodel.named_modules():
                layers.append(name)
            layers: List[str] = list(filter(None, layers))

            # First AV generation on last 2 layers
            inputs = torch.stack((mydata[1], mydata[8], mydata[14]))
            AV.generate_activation(
                tmpdir, mymodel, "model_id_1", layers[1:], inputs, "test", "0"
            )

            av_test = AV._construct_file_search(tmpdir, "model_id_1", identifier="test")
            av_test = glob.glob(av_test)
            self.assertEqual(len(av_test), len(layers[1:]))

            # Second AV generation on first 2 layers.
            # Second layer overlaps with existing activations, should be loaded.
            inputs = torch.stack((mydata[0], mydata[7], mydata[13]))
            AV.generate_activation(
                tmpdir, mymodel, "model_id_1", layers[:2], inputs, "test", "0"
            )

            av_test = AV._construct_file_search(tmpdir, "model_id_1", identifier="test")
            av_test = glob.glob(av_test)
            self.assertEqual(len(av_test), len(layers))

    def test_generate_dataset_activations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            num_features = 4
            low, high = 0, 16
            batch_size = high // 2
            mymodel = BasicLinearReLULinear(num_features)
            mydata = RangeDataset(low, high, num_features)
            layers: List[str] = []
            for name, _module in mymodel.named_modules():
                layers.append(name)
            layers: List[str] = list(filter(None, layers))

            # First AV generation on last 2 layers
            AV.generate_dataset_activations(
                tmpdir,
                mymodel,
                "model_id1",
                layers[1:],
                DataLoader(mydata, batch_size, shuffle=False),
                "src",
            )

            av_src = AV._construct_file_search(
                tmpdir, model_id="model_id1", identifier="src"
            )
            av_src = glob.glob(av_src)
            self.assertEqual(len(av_src), high / batch_size * len(layers[1:]))

            # Second AV generation on first 2 layers.
            # Second layer overlaps with existing activations, should be loaded.
            AV.generate_dataset_activations(
                tmpdir,
                mymodel,
                "model_id1",
                layers[:2],
                DataLoader(mydata, batch_size, shuffle=False),
                "src",
            )

            av_src = AV._construct_file_search(
                tmpdir, model_id="model_id1", identifier="src"
            )
            av_src = glob.glob(av_src)
            self.assertEqual(len(av_src), high / batch_size * len(layers))

    def test_equal_activation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            num_features = 4
            low, high = 0, 16
            mymodel = BasicLinearReLULinear(num_features)
            mydata = RangeDataset(low, high, num_features)
            layers: List[str] = []
            for name, _module in mymodel.named_modules():
                layers.append(name)
            layers: List[str] = list(filter(None, layers))
            # First AV generation on last 2 layers
            test_input = mydata[1].unsqueeze(0)
            act = AV.generate_activation(
                tmpdir, mymodel, "id_1", layers[2], test_input, "test", "0"
            )
            out = mymodel(test_input)
            assertTensorAlmostEqual(self, out, act)
