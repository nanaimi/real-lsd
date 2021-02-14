import os
import gym
import numpy as np
from gym import spaces
from real_lsd.envs.landing import reward, reset_point
from real_lsd.envs.landing.visualization import show_info
from gym_unrealcv.envs.utils import env_unreal
from real_lsd.envs.landing.interaction import Landing

'''
It is a general env for searching target object.

State : raw color image and pose of agent (640x480)

Action:  (MoveTo a certain point on grid)

Done : Collision with ground or with blocking wall(invisible).

Task: Learn to land on appropriate surfaces,
      set appropriate landing surface according to list of targets in settings
'''

class UnrealCvLanding_base(gym.Env):
    # Constructor
    def __init__(self,
                 setting_file,
                 category,
                 reset_type='random',   # testpoint, waypoint, random
                 augment_env=None,        # texture, target, light
                 action_type='Discrete',  # 'Discrete', 'Continuous'
                 observation_type='PoseColor', # 'color', 'depth', 'rgbd', 'PoseColor'
                 reward_type='mask',      # distance, bbox, bbox_distance, 'mask'
                 docker=False,            # True/False
                 resolution=(160, 120)    # Res of window
                 ):

        # load in settings from json
        setting = self.load_env_setting(setting_file)
        self.cam_id = setting['cam_id']
        self.target_list = setting['targets'][category]
        self.trigger_th = setting['trigger_th']                                 # Not Sure about trigger
        self.successful_landing_th = setting['successful_landing_th']
        self.target_object = setting['target_object']
        self.discrete_actions = setting['discrete_actions']
        self.continous_actions = setting['continous_actions']

        self.docker = docker
        self.reset_type = reset_type                                            # Not Sure about reset_type
        self.augment_env = augment_env                                          # Not Sure about augment_env

        # start unreal env
        self.unreal = env_unreal.RunUnreal(ENV_BIN=setting['env_bin'])
        env_ip, env_port = self.unreal.start(docker, resolution)

        # connect UnrealCV
        self.unrealcv = Landing(cam_id=self.cam_id,
                                   port=env_port,
                                   ip=env_ip,
                                   targets=self.target_list,
                                   env=self.unreal.path2env,
                                   resolution=resolution)
        # self.unrealcv.pitch = self.pitch

        #  define action
        self.action_type = action_type
        assert self.action_type == 'Discrete' or self.action_type == 'Continuous'
        if self.action_type == 'Discrete':
            self.action_space = spaces.Discrete(len(self.discrete_actions))
        elif self.action_type == 'Continuous':
            self.action_space = spaces.Box(low=np.array(self.continous_actions['low']),
                                           high=np.array(self.continous_actions['high']))

        # define observation space
        self.observation_type = observation_type
        assert self.observation_type == 'Color' or self.observation_type == 'Depth' or self.observation_type == 'Rgbd' or self.observation_type == 'PoseColor'
        self.observation_space = self.unrealcv.define_observation(self.cam_id, self.observation_type, 'direct')

        # define reward type
        self.reward_type = reward_type
        self.reward_function = reward.Reward(setting)

        # set start position
        self.trigger_count = 0
        current_pose = self.unrealcv.get_pose(self.cam_id)
        self.unrealcv.set_location(self.cam_id, current_pose[:3])
        self.count_steps = 0
        self.targets_pos = self.unrealcv.build_pose_dic(self.target_list)
        # for reset point generation and selection
        self.reset_module = reset_point.ResetPoint(setting, reset_type, current_pose)

    def _step(self, action ):
        info = dict(
            Collision=False,
            Done=False,
            Trigger=0.0,
            Reward=0.0,
            Action=action,
            Pose=[],
            Trajectory=self.trajectory,
            Steps=self.count_steps,
            Target=[],
            Direction=None,
            Waypoints=self.reset_module.waypoints,
            Color=None,
            Depth=None,
        )
        # print("Step function")
        # print("action pre-squeeze", action)
        action = np.squeeze(action)
        # print("action post-squeeze", action)

        if self.action_type == 'Discrete':
            (delt_x, delt_y, delt_z, info['Trigger']) = self.discrete_actions[action]
        else:
            (delt_x, delt_y, delt_z, info['Trigger']) = action
        self.count_steps += 1
        info['Done'] = False

        # take action
        info['Collision'] = self.unrealcv.move_3d(self.cam_id, delt_x, delt_y, delt_z)
        info['Pose'] = self.unrealcv.get_pose(self.cam_id, 'hard')

        if 'mask' in self.reward_type:
            # get segmented image
            object_mask = self.unrealcv.read_image(self.cam_id, 'object_mask')
            # get_mask gets you a binary image, either 0 or 255 per pixel
            mask = self.unrealcv.get_mask(object_mask, self.target_object)
            reward, done = self.reward_function.reward_mask(mask, info['Pose'])
            info['Reward'] = reward
            info['Done'] = done
        # calculate reward according to the distance to target object
        elif 'distance' in self.reward_type:
            info['Reward'] = self.reward_function.reward_distance(distance)
        else:
            info['Reward'] = 0

        # If triggered the agent believes that the episode should be DONE
        if info['Trigger'] > self.trigger_th:
            self.trigger_count += 1
            if self.trigger_count >= 3:
                info['Done'] = True
        else:
            # if collision detected, the episode is done and reward is -1
            if info['Collision'] or self.count_steps >= 150:
                info['Reward'] = -100
                info['Done'] = True

        # Update observation
        state = self.unrealcv.get_observation(self.cam_id, self.observation_type)

        if self.observation_type in ['Color', 'Rgbd', 'PoseColor', 'PoseFeatures']:
            info['Color'] = self.unrealcv.img_color

        if self.observation_type in ['Depth', 'Rgbd']:
            info['Depth'] = self.unrealcv.img_depth

        if self.observation_type in ['PoseFeatures']:
            info['Features'] = self.unrealcv.features

        # save the trajectory
        self.trajectory.append(info['Pose'][:6])
        info['Trajectory'] = self.trajectory

        return state, info['Reward'], info['Done'], info

    # TODO: this is fucked looool
    def _reset(self, ):
        # double check the resetpoint, it is necessary for random reset type
        collision = True
        while collision:
            current_pose = self.reset_module.select_resetpoint()
            self.unrealcv.set_pose(self.cam_id, current_pose)
            collision = self.unrealcv.move_3d(self.cam_id, 40, 40, -20) # WTF

        # nevermind, they just move and then reset it to the pose before moving
        # weird way to check for collisons tho
        self.unrealcv.set_pose(self.cam_id, current_pose)

        state = self.unrealcv.get_observation(self.cam_id, self.observation_type)

        self.trajectory = []
        self.trajectory.append(current_pose)
        self.trigger_count = 0
        self.count_steps = 0

        return state

    def _seed(self, seed=None):
        return seed

    def _render(self, mode='rgb_array', close=False):
        if close==True:
            self.unreal.close()
        return self.unrealcv.img_color

    def _close(self):
        self.unreal.close()

    def _get_action_size(self):
        return len(self.action)

    # TODO: Probably remove
    def select_target_by_distance(self, current_pos, targets_pos):
        # find the nearest target, return distance and targetid
        target_id = list(self.targets_pos.keys())[0]
        distance_min = self.unrealcv.get_distance(targets_pos[target_id], current_pos, 2)
        for key, target_pos in targets_pos.items():
            distance = self.unrealcv.get_distance(target_pos, current_pos, 2)
            if distance < distance_min:
                target_id = key
                distance_min = distance
        return distance_min, target_id

    # TODO: Probably Remove
    # IN: pose of agent and pose of target
    # OUT: direction as yaw angle
    def get_direction(self, current_pose, target_pose):
        y_delt = target_pose[1] - current_pose[1]
        x_delt = target_pose[0] - current_pose[0]
        angle_now = np.arctan2(y_delt, x_delt)/np.pi*180-current_pose[4]
        if angle_now > 180:
            angle_now -= 360
        if angle_now < -180:
            angle_now += 360
        return angle_now

    # IN: filename of setting json in envs/setting directory
    # Out: Dictionary object named setting
    def load_env_setting(self, filename):
        import gym_unrealcv
        gympath = os.path.dirname(gym_unrealcv.__file__)
        gympath = os.path.join(gympath, 'envs/setting', filename)
        f = open(gympath)
        filetype = os.path.splitext(filename)[1]
        if filetype == '.json':
            import json
            setting = json.load(f)
        else:
            print ('unknown type')

        return setting
