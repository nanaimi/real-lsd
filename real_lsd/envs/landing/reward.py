import numpy as np
import cv2
class Reward():
    '''
    define different type reward function
    '''
    def __init__(self, setting):
        self.reward_factor = setting['reward_factor']
        self.reward_th = setting['reward_th']
        self.dis2target_last = 0

    # IN: object mask delivered by unrealcv client, mask, and pose
    # OUT: reward
    def reward_mask(self, mask, pose):
        reward = 0
        done = False
        factor = 10
        print(mask.shape)
        height, width = mask.shape
        tot_num_pixels = height*width
        fov_score = (cv2.sumElems(mask) / 255) / tot_num_pixels

        reward = factor*np.tanh(fov_score*2*np.pi-np.pi)

        if pose[2] < 10:
            reward += 100
            done = True
        else:
            reward -= -(1/10)*pose[2]

        return reward, done

    def reward_bbox(self, boxes):
        reward = 0
        # summarize the reward of each detected box
        for box in boxes:
            reward += self.get_bbox_reward(box)

        if reward > self.reward_th:
            # get ideal target
            reward = min(reward * self.reward_factor, 10)
        elif reward == 0:
            # false trigger
            reward = -1
        else:
            # small target
            reward = 0

        return reward, boxes

    def get_bbox_reward(self, box):
        # get reward of single box considering the size and position of box
        (xmin, ymin), (xmax, ymax) = box
        boxsize = (ymax - ymin) * (xmax - xmin)
        x_c = (xmax + xmin) / 2.0
        x_bias = x_c - 0.5
        discount = max(0, 1 - x_bias ** 2)
        reward = discount * boxsize
        return reward

    def reward_distance(self, dis2target_now):
        reward = (self.dis2target_last - dis2target_now) / max(self.dis2target_last, 100)
        self.dis2target_last = dis2target_now

        return reward
