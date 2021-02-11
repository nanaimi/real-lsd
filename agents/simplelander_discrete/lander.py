import gym

from stable_baselines.common.policies import MlpPolicy
from stable_baselines.common import make_vec_env
from stable_baselines import PPO2
import gym_unrealcv
import real_lsd

import torch

from PPOagent import PPOAgent

use_cuda = torch.cuda.is_available()
device   = torch.device("cuda" if use_cuda else "cpu")

# initialise environment
env = gym.make('MyUnrealLand-cpptestFloorGood-DiscretePoseColor-v0')

num_inputs  = env.observation_space.shape[0]
num_outputs = env.action_space.shape[0]

#Hyper params:
hidden_size      = 256
lr               = 3e-4
num_steps        = 20
mini_batch_size  = 5
ppo_epochs       = 4
threshold_reward = -200 # update/review


agent = PPOAgent(num_inputs,
                num_outputs,
                hidden_size,
                lr,
                num_steps,
                mini_batch_size,
                ppo_epochs,
                threshold_reward,
                std=0.0))

max_frames = 15000
frame_idx  = 0
test_rewards = []


state = env.reset()
early_stop = False


while frame_idx < max_frames and not early_stop:

    log_probs = []
    values    = []
    states    = []
    actions   = []
    rewards   = []
    masks     = []
    # total entropy ? what is interesting about this
    entropy = 0

    for _ in range(num_steps):
        state = torch.FloatTensor(state).to(device)
        dist, value = agent.model(state)

        action = dist.sample()
        next_state, reward, done, _ = env.step(action.cpu().numpy())
        env.render()

        log_prob = dist.log_prob(action)
        entropy += dist.entropy().mean()

        # Append data to arrays
        log_probs.append(log_prob)
        values.append(value)
        rewards.append(torch.FloatTensor(reward).unsqueeze(1).to(device))
        masks.append(torch.FloatTensor(1 - done).unsqueeze(1).to(device))

        states.append(state)
        actions.append(action)

        # next state logic
        state = next_state
        frame_idx += 1

        if frame_idx % 1000 == 0:
            test_reward = np.mean([test_env() for _ in range(10)])
            test_rewards.append(test_reward)
            plot(frame_idx, test_rewards)
            if test_reward > threshold_reward: early_stop = True


    next_state = torch.FloatTensor(next_state).to(device)
    _, next_value = agent.model(next_state)
    returns = agent.compute_gae(next_value, rewards, masks, values)

    returns   = torch.cat(returns).detach()
    log_probs = torch.cat(log_probs).detach()
    values    = torch.cat(values).detach()
    states    = torch.cat(states)
    actions   = torch.cat(actions)
    advantage = returns - values

    agent.ppo_update(ppo_epochs, mini_batch_size, states, actions, log_probs, returns, advantage)






#
# # multiprocess environment
# # example env name
# # UnrealLand-cpptestFloorGood-DiscretePoseColor-v0
# env = gym.make('MyUnrealLand-cpptestFloorGood-DiscretePoseColor-v0')
# # env = make_vec_env('UnrealSearch-RealisticRoomDoor-DiscreteColor-v0', n_envs=1)
#
# # PP02 with mlp network for both actor and critic, both with two layers and 64
# # neurons each
# model = PPO2(MlpPolicy, env, verbose=1)
# model.learn(total_timesteps=2000) # test with fewer timesteps
# model.save("testrun")
#
#
# # Enjoy trained agent
# obs = env.reset()
# while True:
#     action, _states = model.predict(obs)
#     obs, rewards, dones, info = env.step(action)
#     env.render()