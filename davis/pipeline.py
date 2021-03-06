## Basic Python libraries
import argparse
import sys
import os
sys.path.append(os.getcwd() + '/')

## Deep learning and array processing libraries
import numpy as np 
import pandas as pd 
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import torchvision.transforms as transforms
import torchvision.datasets as datasets

## Inner-Project Imports
from base_classifiers.architectures import small_cnn, resnet18
from utils.transforms import *
from davis_utils.estimation import estimation
from davis_utils.inference import inference


def arguments():
    parser = argparse.ArgumentParser(description='Training baseline classifier')
    parser.add_argument('--image_dir', '-I', 
                        default='', type=str, 
                        metavar='ID', help='location of image data')
    parser.add_argument('--network_path', '-NP', 
                        default='', type=str, 
                        metavar='NET', help='path to network pth file')
    parser.add_argument('--tree_path', '-TP', 
                        default='', type=str, 
                        metavar='NET', help='path to tree txt file')
    parser.add_argument('--results_dir', '-R', 
                        default='', type=str, 
                        metavar='RD', help='location to save results')
    parser.add_argument('--dataset', '--data', '-d', 
                        default='tomato', type=str, 
                        metavar='DATA', help='name of data set')
    parser.add_argument('--name', 
                        default='', type=str, 
                        metavar='NAME', help='name of experiment')
    parser.add_argument('--network', '-n', 
                        default='small_cnn', type=str, 
                        metavar='N', choices=['small_cnn', 'resnet18'], 
                        help='network architecture')
    parser.add_argument('--num_bins', '--nbins', 
                        default=10, type=int, 
                        metavar='NB', help='number of histogram bins')
    parser.add_argument('--priors', '-p', 
                        default='equal', type=str, 
                        metavar='P', choices=['equal', 'data', 'manual'], 
                        help='what type of priors are we using')
    parser.add_argument('--confidence', '--conf', 
                        default=0.5, type=float, 
                        metavar='CONF', help='confidence threshold for inference procedure')
    parser.add_argument('--device', '--dev', 
                        default='cuda:0', type=str, 
                        metavar='DEV', choices=['cpu', 'cuda:0'], 
                        help='device id (e.g. \'cpu\', \'cuda:0\'')
    parser.add_argument('--seed', 
                        default=None, type=str, 
                        metavar='S', help='set a seed for reproducability')
    args = vars(parser.parse_args())

    # Ensure necessary paths have been provided
    assert args['image_dir'] != '', f'Must provide a path to an image directory for {args["dataset"]}'
    assert os.path.exists(args['network_path']), f'Must provide a path to a network pth file for {args["dataset"]}'
    assert os.path.exists(args['tree_path']), f'Must provide a path to a tree txt file for {args["dataset"]}'
    assert args['results_dir'] != '', f'Must provide a path to a results directory for {args["dataset"]}'

    # Create the experiment name
    args['name'] = f'{args["dataset"]}_test' if args['name'] == '' else args['name']   

    # Ensure we don't accidentally overwrite anything by checking how many previous experiments share the same name
    directories = [name for name in os.listdir(os.path.abspath(args['results_dir'])) if os.path.isdir(f'{args["results_dir"]}{name}') and args['name'] in name]
    num = len(directories)
    args['name'] = f'{args["name"]}_{num}'

    assert args['num_bins'] > 1, 'Number of histograms should be more than 1'
    assert 0 <= args['confidence'] <= 1, 'Confidence threshold must be between 0 and 1 (inclusive)'

    # Set the device
    if 'cuda' in args['device']:
        assert torch.cuda.is_available(), 'Device set to GPU but CUDA not available'
    args['device'] = torch.device(args['device'])

    # Set a seed if provided
    if args['seed'] is not None:
        args['seed'] = int(args['seed'])
        torch.manual_seed(args['seed'])
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        np.random.seed(args['seed'])

    return args

if __name__ == '__main__':
    # Get arguments
    args = arguments()

    # Create the data transforms for each respective set
    if args['dataset'] == 'tomato':
        transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])])
    elif args['dataset'] == 'corn' or args['dataset'] == 'soybean':                       
        transform = transforms.Compose([AdaptiveCenterCrop(), Resize(size=345), 
                                        transforms.ToTensor(), transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])])
    else:
        raise Exception('Dataset not yet supported')

    # Create the data sets
    train_dataset = datasets.ImageFolder(root=f'{args["image_dir"]}train/', transform=None)
    test_dataset = datasets.ImageFolder(root=f'{args["image_dir"]}test/', transform=transform)
    val_dataset = datasets.ImageFolder(root=f'{args["image_dir"]}val/', transform=transform)

    # Create the DataLoaders from the data sets
    train_dataloader = DataLoader(train_dataset, batch_size=1, shuffle=False)
    test_dataloader = DataLoader(test_dataset, batch_size=1, shuffle=False)
    val_dataloader = DataLoader(val_dataset, batch_size=1, shuffle=False)

    # Create the network and load network state dictionary
    num_classes = len(val_dataset.classes)
    if args['network'] == 'small_cnn':
        network = small_cnn.SmallCNN(num_classes)
    elif args['network'] == 'resnet18':
        network = resnet18.ResNet18(num_classes)
    network.load_state_dict(torch.load(args['network_path'], map_location='cpu'))
    network.eval()

    # Send to device (preferably GPU)
    network = network.to(args['device'])

    # Do the estimation on the validation data
    tree = estimation(tree_path=args['tree_path'], network=network, compute_device=args['device'], train_dataloader=train_dataloader, 
                        val_dataloader=val_dataloader, nbins=args['num_bins'], priors=args['priors'])

    # Perform inference on the test data
    inference(confidence_threshold=args['confidence'], experiment=args['name'], tree=tree, network=network, compute_device=args['device'], 
                dataloader=test_dataloader, nbins=args['num_bins'], results_directory=args['results_dir'], save_results=True)
