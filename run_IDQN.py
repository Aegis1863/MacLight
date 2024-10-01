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
from train.common_train import train_IDQN_agent
from agent.DQN_agent import DQN
from tqdm import trange
from net.net import Qnet
from env.wrap.random_block import BlockStreet
from util.tools import ReplayBuffer
import warnings
warnings.filterwarnings('ignore')

# * ---------------------- 参数 -------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='IDQN 任务')
    parser.add_argument('--model_name', default="IDQN", type=str, help='基本算法名称')
    parser.add_argument('-t', '--task', default="block", type=str, help='任务名称 regular / block')
    parser.add_argument('-r', '--representation', default=False, help='是否采用表征学习')
    parser.add_argument('-b', '--block_num', default=8, type=int, help='封堵街道数')
    parser.add_argument('-l', '--level', default='normal', type=str, help='任务难度 normal/hard')
    parser.add_argument('-w', '--writer', default=0, type=int, help='存档等级, 0: 不存，1: 本地')
    parser.add_argument('--seconds', default=3600, type=int, help='运行时间')
    parser.add_argument('-e', '--episodes', default=80, type=int, help='运行回合数')
    parser.add_argument('-s', '--seed', nargs='+', default=[42, 46], type=int, help='起始种子')
    args = parser.parse_args()

    # 环境相关
    device = "cuda" if torch.cuda.is_available() else "cpu"
    env = sumo_rl.parallel_env(net_file='env/map/ff.net.xml',
                               route_file=f'env/map/ff_{args.level}.rou.xml',
                               num_seconds=args.seconds,
                               use_gui=False,
                               sumo_warnings=False,
                               additional_sumo_cmd='--no-step-log')
    # 神经网络相关
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
        # 更新任务名
        args.task = args.task + '_' + args.level

    # DQN相关
    alg_args = {}
    alg_args['q_lr'] = 1e-3
    alg_args['gamma'] = 0.98  # 时序差分学习率，也作为折算奖励的系数之一
    alg_args['device'] = device
    alg_args['epsilon'] = 0.8
    alg_args['targe_update'] = 5
    alg_args['agent_name'] = agent_name
    pool_size = 10000
    minimal_size = 1000
    batch_size = 20

    # 任务相关
    system_type = sys.platform  # 操作系统

    # * ------------------------ 训练 ----------------------------
    print(f'[ Start >>> task: {args.task} - {args.block_num} | model: {args.model_name} | repre: {args.representation} | device: {device} ]')
    for seed in trange(args.seed[0], args.seed[-1] + 1, mininterval=40, ncols=70):
        evaluator = Evaluator()
        CKP_PATH = f'ckpt/{args.task}/{args.model_name}'
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        magent = {}
        replay_buffer = ReplayBuffer(len(agent_name), state_dim, pool_size, batch_size)
        for idx, agt_name in enumerate(agent_name):
            q_net = Qnet(state_dim, hidden_dim, action_dim).to(device)
            magent[agt_name] = DQN(q_net, alg_args['q_lr'], alg_args['gamma'], alg_args['epsilon'],
                                   alg_args['targe_update'], alg_args['device'])
        return_list, train_time = train_IDQN_agent(env, magent, agent_name, replay_buffer, minimal_size, args.writer,
                                                   args.episodes, seed, CKP_PATH, evaluator,
                                                   )