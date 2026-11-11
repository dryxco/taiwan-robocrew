import unittest
import numpy as np
from server.simulation import Robot

class CupStabilityTests(unittest.TestCase):
    def test_resting_cup_stays_upright_and_remains_dynamic(self):
        robot = Robot('tea')
        for _ in range(12000):
            robot.step(.005)
        positions = []
        for _ in range(400):
            robot.step(.005)
            positions.append(robot.food)
        self.assertLess(float(np.max(np.ptp(positions, axis=0))), .0001)
        self.assertGreater(robot.data.body('food').xmat[8], .999)
        before = robot.food.copy()
        robot.data.qvel[0] = .2
        for _ in range(20):
            robot.step(.005)
        self.assertGreater(float(np.linalg.norm(robot.food-before)), .0005)

if __name__ == '__main__':
    unittest.main()
