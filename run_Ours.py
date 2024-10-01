import os
os.environ['LIBSUMO_AS_TRACI'] = '1'
import argparse
import torch
import gymnasium as gym
import sumo_rl
import random
import sys
import numpy as np
from train.Evaluator import Evaluator
from train.train_ours import train_ours_agent
from agent.Ours_agent import MacLight
from tqdm import trange
from net.net import PolicyNet, ValueNet, VAE
from env.wrap.random_block import BlockStreet
from util.tools import MARLWrap
import warnings
warnings.filterwarnings('ignore')

# * ---------------------- 参数 -------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Ours 任务')
    parser.add_argument('--model_name', default="RPPO", type=str, help='基本算法名称')
    parser.add_argument('-r', '--representation', default=True, help='是否采用表征学习')
    parser.add_argument('-t', '--task', default="block", type=str, help='任务名称 regular / block')
    parser.add_argument('-b', '--block_num', default=8, type=int, help='封堵街道数')
    parser.add_argument('-l', '--level', default='normal', type=str, help='任务难度 normal/hard')
    parser.add_argument('-w', '--writer', default=0, type=int, help='存档等级, 0: 不存，1: 本地')
    parser.add_argument('--seconds', default=3600, type=int, help='运行时间')
    parser.add_argument('-e', '--episodes', default=80, type=int, help='运行回合数')
    parser.add_argument('-s', '--seed', nargs='+', default=[42, 46], type=int, help='起始种子')
    args = parser.parse_args()

    # ENV
    device = "cuda" if torch.cuda.is_available() else "cpu"
    env = sumo_rl.parallel_env(net_file='env/map/ff.net.xml',
                               route_file=f'env/map/ff_{args.level}.rou.xml',
                               num_seconds=args.seconds,
                               use_gui=False,
                               sumo_warnings=False,
                               additional_sumo_cmd='--no-step-log')
    # NN
    agent_name = env.possible_agents
    state_dim = [env.observation_space(i).shape[0] for i in agent_name]
    hidden_dim = [env.observation_space(i).shape[0] * 2 for i in agent_name]
    action_dim = [env.action_space(i).n for i in agent_name]
    if len(set(state_dim)) == 1:
        state_dim = state_dim[0]
        action_dim = action_dim[0]
        hidden_dim = hidden_dim[0]

        if args.task == 'block':
            env = BlockStreet(env, args.block_num, args.seconds)
        else:
            args.block_num = None
        args.model_name = 'Ours'
        latent_dim = 10
        args.task = args.task + '_' + args.level

    # PPO
    alg_args = {}
    alg_args['actor_lr'] = 1e-4
    alg_args['critic_lr'] = 1e-3
    alg_args['lmbda'] = 0.95
    alg_args['gamma'] = 0.99
    alg_args['device'] = device
    alg_args['epochs'] = 10
    alg_args['eps'] = 0.2
    alg_args['agent_name'] = agent_name

    system_type = sys.platform

    # * ------------------------ Train ----------------------------
    print(f'[ Start >>> task: {args.task} - {args.block_num} | model: {args.model_name} | repre: {args.representation} | device: {device} ]')
    for seed in trange(args.seed[0], args.seed[-1] + 1, mininterval=40, ncols=70):
        evaluator = Evaluator()
        CKP_PATH = f'ckpt/{args.task}/{args.model_name}'
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        vae = VAE(state_dim, latent_dim).to(device) if args.representation else None
        magent = MARLWrap('I', MacLight, alg_args, PolicyNet, ValueNet,
                          state_dim, hidden_dim, action_dim, latent_dim=latent_dim)
        return_list, train_time = train_ours_agent(env, magent, agent_name, vae, args.writer,
                                                   args.episodes, seed, CKP_PATH, evaluator,
                                                   )