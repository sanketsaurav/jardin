from setuptools import setup

setup(name = 'jardin',
      version = '0.1',
      description = 'A dataframe-base ORM',
      packages = ['jardin'],
      install_requires = [
      'pandas',
      'numpy',
      'psycopg2'
      ])