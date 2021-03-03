import os
import gym
import time
import torch
import torch.nn as nn
import pickle
import numpy as np
import glog as log
import subprocess

import gym_unrealcv
import real_lsd

from PPOagent import PPOAgent


'''---------------------------Helper functions--------------------'''
def save_obj(obj, filename):
    dir = 'data'
    # path = os.getcwd()
    PATH = '/media/scratch1/nasib'

    if dir not in os.listdir(PATH):
        PATH =  os.path.join(PATH, dir)
        os.mkdir(PATH)
    else:
        PATH =  os.path.join(PATH, dir)

    abs_file_path = PATH + '/' + filename + '.pkl'
    with open(abs_file_path, 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

    return filename

'''---------------------------------------------------------------'''

# Set to INFO for debugging
log.setLevel("WARN")

# initialise environment
env = gym.make('MyUnrealLand-cpptestFloorGood-DiscreteHeightFeatures-v0')

print("Observation Space:", env.observation_space, "dimension of observation:", env.observation_space.shape[0])

num_inputs  = env.observation_space.shape[0]

print("Action Space:", env.action_space, "Number of actions:", env.action_space.n)

num_outputs = env.action_space.n

# only actions that don't go up in z are viable
prob_per_viable_action = np.float32(1/18)

# Create probability array
probabilities = np.zeros(num_outputs)
probabilities[:3] = prob_per_viable_action
probabilities[4:8] = prob_per_viable_action
probabilities[10:14] = prob_per_viable_action
probabilities[16:19] = prob_per_viable_action
probabilities[22] = prob_per_viable_action
probabilities[24:] = prob_per_viable_action

# Define distribution
probabilities = torch.tensor(probabilities)
action_dist = Categorical(probabilities)

sample = action_dist.sample()
print("sampled action: {}".format(sample))

# Testing the policy after training
num_tests = 1
episodes_per_test = 50
successful_episodes = 0

log.warn("Time to test.")

for test in range(num_tests):
    episode_count = 0
    num_test_episodes = episodes_per_test

    episodes = {}

    state = env.reset()

    while episode_count < num_test_episodes:

        done = False
        episode = {}

        # poses     = [start_pose]
        states    = [state]
        dists     = []
        values    = []
        actions   = []
        rewards   = []
        log_probs = []
        traj      = []

        while not done:
            action = 0
            states.append(state)

            action = action_dist.sample()
            log.info("action type: {}".format(action))

            next_state, reward, done, info = env.step(action.cpu().numpy())

            actions.append(action.cpu().numpy())
            rewards.append(reward)

            # next state logic
            if done:
                if info['Success']:
                    successful_episodes += 1
                traj = info['Trajectory']
                state = env.reset()
                episode_count += 1
            else:
                state = next_state

        # episode['poses']    = poses
        episode['states']   = states
        episode['actions']  = actions
        episode['rewards']  = rewards
        episode['trajectory']= traj

        key = 'episode_{}'.format(episode_count)
        episodes[key] = episode

    filename = time.strftime("%Y%m%d_%H%M%S") + '{}'.format(test)
    log.warn("About to save the test data.")
    file = save_obj(episodes, filename)
    del episodes
    log.warn("Successes out of {}: {}".format(num_tests*episodes_per_test, successful_episodes))
    # print(load_obj(file))

log.warn("Done Testing.")

env.close()
