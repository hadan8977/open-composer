source: https://orion.readthedocs.io/en/latest/code/algo/asha.html
fetched_utc: 2026-10-04T18:37:52Z

Asynchronous Successive Halving Algorithm — orion v0.2.6.post323 documentation

             orion

                latest

Welcome

Getting Started

Integration

Python API

Optimize

Scaling up

Search Space

Algorithms

Monitoring

Next steps

Installing Oríon

Bleeding edge

Database Setup

Configuring the database

Testing the configuration

Supported databases

EphemeralDB

Arguments

PickledDB

Arguments

MongoDB

Arguments

Installing MongoDB

MongoDB Atlas

Upgrading the database

User Guide

Overview

Integrate

Orion customization

user_script_config

working_dir

Language compatibility

Command-line templating

Environment variables

Optimize

Command line API

Python APIs

Service API

Framework API

Algorithms

Selecting and Configuring

Included Algorithms

Random Search

Configuration

Grid Search

Configuration

Hyperband

Configuration

ASHA

Configuration

BOHB

Configuration

DEHB

Configuration

Population Based Training (PBT)

Configuration

Population Based Bandits (PB2)

Configuration

TPE

Configuration

Ax

Configuration

Evolution-ES

Configuration

MOFA

Configuration

Nevergrad

HEBO

Configuration

Algorithm Plugins

Scikit-Optimize

Robust Bayesian Optimization

Parallel Strategies

NoParallelStrategy

StubParallelStrategy

MaxParallelStrategy

MeanParallelStrategy

StatusBasedParallelStrategy

Search Space

Priors

uniform(low, high)

loguniform(low, high)

normal(loc, scale)

gaussian(loc, scale)

choices(options)

fidelity(low, high, base=2)

Dimension Types

Real

Integer

Categorical

Fidelity

Special arguments

discrete

default_value

precision

shape

Configuration

Commandline

Configuration file

Notes

Transformations

Real

Integer

Conditional dependencies

References

Monitoring

Commands for terminal

list Overview of all experiments

Configuration

Basic Usage

The --name argument

status Overview of trials for experiments

Basic Usage

The --all Argument

The --collapse Argument

The --name Argument

status and the experiment tree

info Detailed information about experiments

The --name argument

The --version argument

Library API

Results

Iterative Results with EVC

Web API

Authentication

Runtime

Experiments

Trials

Plots

Benchmarks

Database dumping

Database loading

Import progression

Errors

Visualizations

Examples

Regret curves

Parallel Coordinates

Special cases

Local Parameter Importance

Special cases

Partial Dependencies

Options

Special cases

How-tos

How-tos

How to plot.

How to save

How to share with chart studio

Benchmark

Experiment Version Control

Source of conflicts

Iterative Results

Storage

Commands

setup Storage configuration

test Test storage configuration

rm Delete data from storage

set Change value of data in storage

release algorithm lock

upgrade Upgrade database scheme

dump Export database content

load Import database content

Python APIs

ExperimentClient

to_pandas

fetch_trials

fetch_trials_by_status

fetch_noncompleted_trials

get_trial

insert

Storage

update_experiment

fetch_experiments

delete_experiment

register_trial

reserve_trial

fetch_trials

delete_trials

get_trial

update_trials

update_trial

fetch_lost_trials

fetch_pending_trials

fetch_noncompleted_trials

fetch_trials_by_status

count_completed_trials

count_broken_trials

set_trial_status

Database

read

write

remove

read_and_write

Advanced Configuration

Full Example of Global Configuration

Database

name

type

host

port

Experiment

name

version

user

max_trials

worker_trials

max_broken

working_dir

algorithm

strategy

Worker

n_workers

pool_size

executor

executor_configuration

heartbeat

max_trials

max_broken

idle_timeout

max_idle_time

interrupt_signal_code

user_script_config

Experiment Version Control

enable

auto_resolution

manual_resolution

non_monitored_arguments

ignore_code_changes

algorithm_change

code_change_type

cli_change_type

config_change_type

orion_version_change

Parallel Workers

Executor backends

Joblib

Dask

Tutorials

Scikit-learn

Sample script

Enter Orion

Updating the script

Updating the script call

Viewing the results

Python API basics

Further readings

PyTorch MNIST

Installation and setup

Adapting the code for Oríon

Execution

Results

Notes

Debugging

Checkpointing trials

With command line

Training code

HPO code

Analysis

Scaling workers

Joblib

Dask

Running on HPC

Parallel optimization using arrays

SSH tunnels

Notes for MongoDB

SSL

Replica Sets

PyTorch A2C PPO ACKTR

Intro

What to change

How to search for hyperparameters

Plugins

Overview

Installing

Algorithms

Skopt algorithms

Developing algorithms

Usage

Implementation

Tests

API Reference

Algorithm modules

Space search

Search space of optimization problems

Categorical

Categorical.cardinality

Categorical.cast()

Categorical.get_cardinality()

Categorical.get_prior

Categorical.get_prior_string()

Categorical.interval()

Categorical.prior_name

Categorical.sample()

Dimension

Dimension.cardinality

Dimension.cast()

Dimension.default_value

Dimension.get_prior_string()

Dimension.get_string()

Dimension.interval()

Dimension.name

Dimension.prior_name

Dimension.sample()

Dimension.shape

Dimension.type

Dimension.validate()

Fidelity

Fidelity.cardinality

Fidelity.cast()

Fidelity.default_value

Fidelity.get_cardinality()

Fidelity.get_prior_string()

Fidelity.interval()

Fidelity.sample()

Fidelity.validate()

Integer

Integer.cardinality

Integer.cast()

Integer.get_cardinality()

Integer.get_prior_string()

Integer.prior_name

Real

Real.cardinality

Real.cast()

Real.get_cardinality()

Real.get_prior_string()

Real.interval()

Real.sample()

Space

Space.assert_contains()

Space.cardinality

Space.configuration

Space.contains

Space.interval()

Space.items()

Space.keys()

Space.register()

Space.sample()

Space.values()

SpaceConverter

SpaceConverter.categorical()

SpaceConverter.convert_dimension()

SpaceConverter.dimension()

SpaceConverter.fidelity()

SpaceConverter.integer()

SpaceConverter.real()

SpaceConverter.space()

check_random_state()

to_orionspace()

Base definition of algorithms

BaseAlgorithm

BaseAlgorithm.configuration

BaseAlgorithm.fidelity_index

BaseAlgorithm.get_id()

BaseAlgorithm.has_completed_max_trials

BaseAlgorithm.has_observed()

BaseAlgorithm.has_suggested()

BaseAlgorithm.has_suggested_all_possible_values()

BaseAlgorithm.is_done

BaseAlgorithm.judge()

BaseAlgorithm.n_observed

BaseAlgorithm.n_suggested

BaseAlgorithm.observe()

BaseAlgorithm.register()

BaseAlgorithm.score()

BaseAlgorithm.seed_rng()

BaseAlgorithm.set_state()

BaseAlgorithm.should_suspend()

BaseAlgorithm.space

BaseAlgorithm.state_dict

BaseAlgorithm.suggest()

BaseAlgorithm.unwrapped

Random Search Algorithm

Random

Random.seed_rng()

Random.set_state()

Random.state_dict

Random.suggest()

Grid Search Algorithm

GridSearch

GridSearch.build_grid()

GridSearch.configuration

GridSearch.is_done

GridSearch.set_state()

GridSearch.state_dict

GridSearch.suggest()

categorical_grid()

discrete_grid()

grid()

real_grid()

Hyperband Algorithm

BudgetTuple

BudgetTuple.n_trials

BudgetTuple.resource_budget

Hyperband

Hyperband.executed_times

Hyperband.fidelity_index

Hyperband.is_done

Hyperband.observe()

Hyperband.sample_from_bracket()

Hyperband.seed_rng()

Hyperband.set_state()

Hyperband.state_dict

Hyperband.suggest()

HyperbandBracket

HyperbandBracket.get_candidates()

HyperbandBracket.get_trial_max_resource()

HyperbandBracket.has_rung_filled()

HyperbandBracket.is_done

HyperbandBracket.is_filled

HyperbandBracket.is_ready()

HyperbandBracket.promote()

HyperbandBracket.register()

HyperbandBracket.seed_rng()

RungDict

compute_budgets()

display_budgets()

Asynchronous Successive Halving Algorithm

ASHA

ASHA.suggest()

ASHABracket

ASHABracket.get_candidates()

ASHABracket.is_filled

ASHABracket.is_ready()

ASHABracket.promote()

compute_budgets()

DEHB

DEHB

DEHB.is_done

DEHB.observe()

DEHB.observe_one()

DEHB.sample_to_trial()

DEHB.seed_rng()

DEHB.set_state()

DEHB.state_dict

DEHB.suggest()

SHBracketManager

SHBracketManager.complete_job()

SHBracketManagerImpl

BOHB

BOHB

BOHB.is_done

BOHB.observe()

BOHB.seed_rng()

BOHB.set_state()

BOHB.state_dict

BOHB.suggest()

Population Based Training

Population Based Training

PBT

LineageNode

LineageNode

Lineages

Lineages

Exploit classes for Population Based Training

BaseExploit

PipelineExploit

TruncateExploit

BacktrackExploit

Explore classes for Population Based Training

BaseExplore

PipelineExplore

PerturbExplore

ResampleExplore

Population Based Bandits

Population Based Bandits

PB2

PB2 Utils

TVSquaredExp

UCB()

normalize()

optimize_acq()

select_config()

select_length()

standardize()

TPE Algorithm

CategoricalSampler

CategoricalSampler.get_loglikelis()

CategoricalSampler.sample()

GMMSampler

GMMSampler.get_loglikelis()

GMMSampler.sample()

TPE

TPE.seed_rng()

TPE.set_state()

TPE.split_trials()

TPE.state_dict

TPE.suggest()

adaptive_parzen_estimator()

compute_max_ei_point()

ramp_up_weights()

Ax

AxOptimizer

AxOptimizer.get_client()

AxOptimizer.observe()

AxOptimizer.reverse_params()

AxOptimizer.seed_rng()

AxOptimizer.set_state()

AxOptimizer.state_dict

AxOptimizer.suggest()

AxOptimizer.transform_params()

MOFA Algorithm

orion.algo.mofa.mofa – MOFA

MOFA

MOFA.is_done

MOFA.observe()

MOFA.seed_rng()

MOFA.set_state()

MOFA.state_dict

MOFA.suggest()

get_factorial_importance_analysis()

get_factorial_performance_analysis()

select_new_region_of_interest()

Nevergrad

NevergradOptimizer

NevergradOptimizer.is_done

NevergradOptimizer.observe()

NevergradOptimizer.seed_rng()

NevergradOptimizer.set_state()

NevergradOptimizer.state_dict

NevergradOptimizer.suggest()

Parallel Strategy

Registries

HEBO

HEBO

HEBO.Parameters

HEBO.observe()

HEBO.seed_rng()

HEBO.set_state()

HEBO.state_dict

HEBO.suggest()

Analysis

Base utils

Base tools to compute diverse analysis

average()

flatten_numpy()

flatten_params()

ranking()

to_numpy()

train_regressor()

Local Parameter Importance

Provide tools to calculate Local Parameter Importance

Partial Dependencies

Tools to compute Partial Dependency

Regret

Provide tools to calculate regret

Provides HPO analysis tools

average()

lpi()

partial_dependency()

ranking()

regret()

Benchmark modules

Benchmark definition

Benchmark

Benchmark.analysis()

Benchmark.configuration

Benchmark.executor

Benchmark.get_experiments()

Benchmark.id

Benchmark.process()

Benchmark.setup_studies()

Benchmark.status()

Study

Study.analysis()

Study.execute()

Study.get_experiments()

Study.setup_experiments()

Study.status()

Benchmark Client

Benchmark client

get_or_create_benchmark()

Task modules

Benchmark Tasks definition

BenchmarkTask

BenchmarkTask.__call__()

BenchmarkTask.call()

BenchmarkTask.configuration

BenchmarkTask.get_search_space()

BenchmarkTask.max_trials

Branin

Branin.call()

Branin.get_search_space()

CarromTable

CarromTable.call()

CarromTable.get_search_space()

EggHolder

EggHolder.call()

EggHolder.get_search_space()

Forrester

Forrester.call()

Forrester.get_search_space()

RosenBrock

RosenBrock.call()

RosenBrock.get_search_space()

Base definition of tasks

Base definition of Task

BenchmarkTask

Branin

Task for Branin Function

Branin

CarromTable

Task for CarromTable Function

CarromTable

EggHolder

Task for EggHolder Function

EggHolder

RosenBrock

Task for RosenBrock Function

RosenBrock

Forrester

Forrester

Profet Task modules

ProfetFcNetTask

ProfetForresterTask

ProfetSvmTask

ProfetTask

ProfetXgBoostTask

Base definition of a Profet task

Utilities for training the Profet meta-model

Assessment modules

Benchmark Assessments definition

AverageRank

AverageRank.analysis()

AverageResult

AverageResult.analysis()

BenchmarkAssessment

BenchmarkAssessment.analysis()

BenchmarkAssessment.configuration

BenchmarkAssessment.get_executor()

BenchmarkAssessment.repetitions

ParallelAssessment

ParallelAssessment.analysis()

ParallelAssessment.configuration

ParallelAssessment.get_executor()

Base definition of assessments

Base definition of Assessment

BenchmarkAssessment

Average Rank

Average Rank Assessment

AverageRank

Average Result

Average Rank Assessment

AverageResult

Average Rank

Parallel Advantage Assessment

ParallelAssessment

Client helper functions

Commandline client

Helper function for returning results from script

interrupt_trial()

report_bad_trial()

report_objective()

report_results()

Experiment client

Experiment wrapper client

ExperimentClient

ExperimentClient.algorithm

ExperimentClient.close()

ExperimentClient.configuration

ExperimentClient.executor

ExperimentClient.fetch_noncompleted_trials()

ExperimentClient.fetch_pending_trials()

ExperimentClient.fetch_trials()

ExperimentClient.fetch_trials_by_status()

ExperimentClient.get_trial()

ExperimentClient.id

ExperimentClient.insert()

ExperimentClient.is_broken

ExperimentClient.is_done

ExperimentClient.max_broken

ExperimentClient.max_trials

ExperimentClient.metadata

ExperimentClient.mode

ExperimentClient.name

ExperimentClient.node

ExperimentClient.observe()

ExperimentClient.producer

ExperimentClient.refers

ExperimentClient.release()

ExperimentClient.reserve()

ExperimentClient.space

ExperimentClient.stats

ExperimentClient.storage

ExperimentClient.suggest()

ExperimentClient.tmp_executor()

ExperimentClient.to_pandas()

ExperimentClient.version

ExperimentClient.working_dir

ExperimentClient.workon()

reserve_trial()

Helper function to insert new trials

Routines for manual interaction with database

insert_trials()

Python API

build_experiment()

create_experiment()

get_experiment()

interrupt_trial()

report_bad_trial()

report_objective()

report_results()

workon()

Core of Oríon

build_config()

define_config()

define_database_config()

define_evc_config()

define_experiment_config()

define_frontends_uri_config()

define_storage_config()

define_worker_config()

Worker and its components

Consumer

Evaluate objective on a set of parameters

Consumer

ExecutionError

Experiment

Description of an optimization attempt

Experiment

ExperimentStats

Primary algorithm

create_algo()

Producer

Produce and register samples to try

Producer

Dimension transformations

Perform transformations on Dimensions

Compose

Enumerate

Identity

Linearize

OneHotEncode

Precision

Quantize

ReshapedDimension

ReshapedSpace

Reverse

TransformedDimension

TransformedSpace

Transformer

View

build_required_space()

build_transform()

change_trial_params()

reshape()

transform()

Trial

Container class for Trial entity

AlreadyReleased

Trial

validate_status()

Trial Pacemaker

Trial Pacemaker

TrialPacemaker

Experiment Version Control

Experiment Version Control System

Experiment Node

Experiment node for EVC

ExperimentNode

adapt_trials()

Adapters for trials compatibility between experiments

Adapters to connect experiments within the EVC system

AlgorithmChange

BaseAdapter

CodeChange

CommandLineChange

CompositeAdapter

DimensionAddition

DimensionDeletion

DimensionPriorChange

DimensionRenaming

OrionVersionChange

ScriptConfigChange

apply_if_valid()

Conflicts detection and resolutions for creation of adapters

Description and resolution of configuration conflicts

AlgorithmConflict

ChangedDimensionConflict

CodeConflict

CommandLineConflict

Conflict

Conflicts

ExperimentNameConflict

MissingDimensionConflict

NewDimensionConflict

OrionVersionConflict

Resolution

ScriptConfigConflict

detect_conflicts()

Input/Output

Input/output functions for interaction with user’s script

Databases

MongoDB database

PickledDB database

EphemeralDB Database

Wrappers for database frameworks

Database

DatabaseError

DatabaseTimeout

DuplicateKeyError

OutdatedDatabaseError

ReadOnlyDB

Configuration converter

Parse and generate user script’s configuration

BaseConverter

GenericConverter

JSONConverter

YAMLConverter

infer_converter_from_file_type()

Space Builder

Create Space objects from configuration

DimensionBuilder

SpaceBuilder

replace_key_in_order()

Parsing of experiment configuration

Configuration parsing and resolving

fetch_config()

fetch_config_from_cmdargs()

fetch_env_vars()

fetch_metadata()

fetch_user_repo()

infer_versioning_metadata()

is_exe()

merge_configs()

update_metadata()

Experiment Builder

Create experiment from user options

ExperimentBuilder

build()

build_from_args()

clean_config()

get_cmd_config()

get_from_args()

load()

merge_algorithm_config()

merge_producer_config()

Experiment Branch Builder

Module offering an API to solve conflicts

ExperimentBranchBuilder

Interactive commands

Branching Prompt

Command line

Functions that define console scripts

load_modules_parser()

main()

Base definitions for command line

Base class and function utilities for cli

OrionArgsParser

get_basic_args_group()

get_user_args_group()

hunt command

Module running the optimization command

add_subparser()

main()

on_error()

workon()

insert command

Module to insert new trials

add_subparser()

main()

init-only command

Module running the init_only command

add_subparser()

main()

db commands

Module containing database related operations

add_subparser()

load_modules_parser()

setup command

db test command

db upgrade command

db rm command

db set command

db release command

Arguments for handling of branching events

Function utilities for evc in cli

fetch_branching_configuration()

get_branching_args_group()

Utilities

Exceptions

Custom exceptions for Oríon

BranchingEvent

BrokenExperiment

CheckError

CompletedExperiment

InexecutableUserScript

InvalidResult

LazyWorkers

MissingResultFile

NoConfigurationError

NoNameError

RaceCondition

ReservationRaceCondition

ReservationTimeout

UnsupportedOperation

WaitingForTrials

Format trials

Utility functions for formatting data

dict_to_trial()

get_trial_results()

standard_param_name()

trial_to_tuple()

tuple_to_trial()

Format terminal

Utility functions for formatting prints to terminal

format_algorithm()

format_commandline()

format_config()

format_dict()

format_identification()

format_info()

format_list()

format_metadata()

format_refers()

format_space()

format_stats()

format_title()

get_trial_params()

Singleton

Singleton helpers and boilerplate

AbstractSingletonType

GenericSingletonFactory

SingletonAlreadyInstantiatedError

SingletonFactory

SingletonNotInstantiatedError

SingletonType

Generic Tree

Tree data structure

DepthFirstTraversal()

PreOrderTraversal()

TreeNode

flattened()

Package-wide useful routines

Factory

Factory.__call__()

GenericFactory

GenericFactory.create()

GenericFactory.get_class()

GenericFactory.get_classes()

compute_identity()

float_to_digits_list()

generate_temporary_file()

get_all_subclasses()

get_all_types()

nesteddict()

sigterm_as_interrupt()

Executor modules

Base

Base Executor

AsyncException

AsyncException.value

AsyncResult

BaseExecutor

BaseExecutor.async_get()

BaseExecutor.submit()

BaseExecutor.wait()

ExecutorClosed

Future

Future.get()

Future.ready()

Future.successful()

Future.wait()

Dask Executor

Dask

Dask.async_get()

Dask.submit()

Dask.wait()

Joblib Executor

Pool

PoolExecutor

PoolExecutor.async_get()

PoolExecutor.submit()

PoolExecutor.wait()

ThreadPool

Base

Executor without parallelism for debugging

SingleExecutor

SingleExecutor.async_get()

SingleExecutor.close()

SingleExecutor.submit()

SingleExecutor.wait()

Joblib Executor

Joblib

Plotting

Plotting Base Backend

Provides public plotting API

PlotAccessor

PlotAccessor.__call__()

PlotAccessor.lpi()

PlotAccessor.parallel_coordinates()

PlotAccessor.partial_dependencies()

PlotAccessor.regret()

durations()

lpi()

parallel_assessment()

parallel_coordinates()

partial_dependencies()

rankings()

regret()

regrets()

Plotly backend

Plotly backend for plotting methods

build_durations_frame()

build_parallel_frame()

build_regrets_frame()

lpi()

parallel_coordinates()

partial_dependencies()

rankings()

regret()

regrets()

Storage Protocol

Base

Generic Storage Protocol

Examples

BaseStorageProtocol

BaseStorageProtocol.acquire_algorithm_lock()

BaseStorageProtocol.count_broken_trials()

BaseStorageProtocol.count_completed_trials()

BaseStorageProtocol.create_benchmark()

BaseStorageProtocol.create_experiment()

BaseStorageProtocol.delete_algorithm_lock()

BaseStorageProtocol.delete_benchmark()

BaseStorageProtocol.delete_experiment()

BaseStorageProtocol.delete_trials()

BaseStorageProtocol.fetch_benchmark()

BaseStorageProtocol.fetch_experiments()

BaseStorageProtocol.fetch_lost_trials()

BaseStorageProtocol.fetch_noncompleted_trials()

BaseStorageProtocol.fetch_pending_trials()

BaseStorageProtocol.fetch_trials()

BaseStorageProtocol.fetch_trials_by_status()

BaseStorageProtocol.get_algorithm_lock_info()

BaseStorageProtocol.get_trial()

BaseStorageProtocol.push_trial_results()

BaseStorageProtocol.register_trial()

BaseStorageProtocol.release_algorithm_lock()

BaseStorageProtocol.reserve_trial()

BaseStorageProtocol.retrieve_result()

BaseStorageProtocol.set_trial_status()

BaseStorageProtocol.update_experiment()

BaseStorageProtocol.update_heartbeat()

BaseStorageProtocol.update_trial()

BaseStorageProtocol.update_trials()

BaseStorageProtocol.write_algorithm_lock()

FailedUpdate

LockAcquisitionTimeout

LockedAlgorithmState

LockedAlgorithmState.reset()

LockedAlgorithmState.set_state()

LockedAlgorithmState.state

MissingArguments

ReadOnlyStorageProtocol

get_trial_uid_and_exp()

get_uid()

setup_storage()

Legacy Database

Legacy storage

Legacy

Legacy.acquire_algorithm_lock()

Legacy.count_broken_trials()

Legacy.count_completed_trials()

Legacy.create_benchmark()

Legacy.create_experiment()

Legacy.delete_algorithm_lock()

Legacy.delete_benchmark()

Legacy.delete_experiment()

Legacy.delete_trials()

Legacy.fetch_benchmark()

Legacy.fetch_experiments()

Legacy.fetch_lost_trials()

Legacy.fetch_noncompleted_trials()

Legacy.fetch_pending_trials()

Legacy.fetch_trials()

Legacy.fetch_trials_by_status()

Legacy.get_algorithm_lock_info()

Legacy.get_trial()

Legacy.push_trial_results()

Legacy.register_trial()

Legacy.release_algorithm_lock()

Legacy.reserve_trial()

Legacy.retrieve_result()

Legacy.set_trial_status()

Legacy.update_experiment()

Legacy.update_heartbeat()

Legacy.update_trial()

Legacy.update_trials()

Legacy.write_algorithm_lock()

setup_database()

Track

Track Storage Protocol

Track

Track.acquire_algorithm_lock()

Track.count_broken_trials()

Track.count_completed_trials()

Track.create_experiment()

Track.fetch_experiments()

Track.fetch_lost_trials()

Track.fetch_noncompleted_trials()

Track.fetch_pending_trials()

Track.fetch_trials()

Track.fetch_trials_by_status()

Track.get_trial()

Track.push_trial_results()

Track.register_trial()

Track.reserve_trial()

Track.retrieve_result()

Track.set_trial_status()

Track.update_experiment()

Track.update_heartbeat()

Track.update_trial()

Track.update_trials()

TrialAdapter

TrialAdapter.end_time

TrialAdapter.experiment

TrialAdapter.gradient

TrialAdapter.hash_params

TrialAdapter.heartbeat

TrialAdapter.id

TrialAdapter.objective

TrialAdapter.params

TrialAdapter.parents

TrialAdapter.results

TrialAdapter.status

TrialAdapter.submit_time

TrialAdapter.to_dict()

add_leading_slash()

convert_track_status()

experiment_uid()

get_track_status()

remove_leading_slash()

to_epoch()

Testing

Algorithms

BaseAlgoTests

BaseAlgoTests.algo_type

BaseAlgoTests.assert_dim_type_supported()

BaseAlgoTests.create_algo()

BaseAlgoTests.create_space()

BaseAlgoTests.force_observe()

BaseAlgoTests.get_num()

BaseAlgoTests.objective

BaseAlgoTests.observe_trials()

BaseAlgoTests.phases

BaseAlgoTests.set_phases()

BaseAlgoTests.test_broken_trials()

BaseAlgoTests.test_cat_data()

BaseAlgoTests.test_configuration()

BaseAlgoTests.test_get_id()

BaseAlgoTests.test_has_observed()

BaseAlgoTests.test_has_observed_statedict()

BaseAlgoTests.test_has_suggested()

BaseAlgoTests.test_has_suggested_statedict()

BaseAlgoTests.test_int_data()

BaseAlgoTests.test_is_done_cardinality()

BaseAlgoTests.test_is_done_max_trials()

BaseAlgoTests.test_logint_data()

BaseAlgoTests.test_logreal_data()

BaseAlgoTests.test_n_observed()

BaseAlgoTests.test_n_suggested()

BaseAlgoTests.test_observe()

BaseAlgoTests.test_optimize_branin()

BaseAlgoTests.test_real_data()

BaseAlgoTests.test_seed_rng()

BaseAlgoTests.test_seed_rng_init()

BaseAlgoTests.test_shape_data()

BaseAlgoTests.test_state_dict()

BaseAlgoTests.test_suggest_n()

BaseAlgoTests.update_space()

BaseParallelStrategyTests

BaseParallelStrategyTests.create_strategy()

BaseParallelStrategyTests.get_corrupted_trial()

BaseParallelStrategyTests.get_noncompleted_trial()

BaseParallelStrategyTests.get_trials()

BaseParallelStrategyTests.test_configuration()

BaseParallelStrategyTests.test_handle_corrupted_trials()

BaseParallelStrategyTests.test_infer_no_history()

BaseParallelStrategyTests.test_state_dict()

BaseParallelStrategyTests.test_strategy_value()

TestPhase

TestPhase.end_n_trials

TestPhase.length

TestPhase.method_to_spy

TestPhase.n_trials

TestPhase.name

customized_mutate_example()

first_phase_only()

last_phase_only()

Plotting

Plotting testing support module

assert_durations_plot()

assert_lpi_plot()

assert_parallel_coordinates_plot()

assert_partial_dependencies_plot()

assert_rankings_plot()

assert_regret_plot()

assert_regrets_plot()

Space

build_space()

dim1()

dim2()

dim3()

dim4()

State (storage)

Mocks Oríon’s runtime

BaseOrionState

BaseOrionState.add_experiments()

BaseOrionState.add_trials()

BaseOrionState.cleanup()

BaseOrionState.get_experiment()

BaseOrionState.get_trial()

BaseOrionState.init()

BaseOrionState.load_experience_configuration()

BaseOrionState.make_config()

BaseOrionState.setup_storage()

LegacyOrionState

LegacyOrionState.cleanup()

LegacyOrionState.database

LegacyOrionState.get_experiment()

LegacyOrionState.init()

OrionState()

Common testing support module

MockDatetime

MockDatetime.utcnow()

create_experiment()

default_datetime()

falcon_client()

generate_benchmark_experiments_trials()

generate_trials()

mock_space_iterate()

mocked_datetime()

Developer Guide

Overview

Getting started

Oríon

Database

Verifying the installation

About tox

Conventions

Coding standard

Version Control Guidelines

Synchronization

Documenting standard

Repository standard

Versioning standard

GitHub labels

Topic

Addition

Improvement

Problems

Status

Discussion

Community

Priority

Inactive

Testing

Running tests

Stress Tests

Execution

Results

Documenting

Updating README.rst

Writing examples

Building documentation

Continuous Integration

Releasing

Creating a release candidate

Making the release

After the release

Logos

Logo with grid

Logo without grid

Icons

          orion

Docs »

Algorithm modules »

Asynchronous Successive Halving Algorithm

               Edit on GitHub

        Next 

         Previous

Asynchronous Successive Halving Algorithm¶

ASHA hyperparameter

class orion.algo.asha.ASHA(space: Space, seed: int | Sequence[int] | None = None, num_rungs: int | None = None, num_brackets: int = 1, repetitions: int | float = inf)[source]¶

Asynchronous Successive Halving Algorithm

A simple and robust hyperparameter tuning algorithm with solid theoretical underpinnings
that exploits parallelism and aggressive early-stopping.

For more information on the algorithm, see original paper at https://arxiv.org/abs/1810.05934.

Li, Liam, et al. “Massively parallel hyperparameter tuning.”
arXiv preprint arXiv:1810.05934 (2018)

Parameters

space: `orion.algo.space.Space`
Optimisation space with priors for each dimension.

seed: None, int or sequence of int
Seed for the random number generator used to sample new trials.
Default: None

num_rungs: int, optional
Number of rungs for the largest bracket. If not defined, it will be equal to (base + 1)
of the fidelity dimension. In the original paper,
num_rungs == log(fidelity.high/fidelity.low) / log(fidelity.base) + 1.
Default: log(fidelity.high/fidelity.low) / log(fidelity.base) + 1

num_brackets: int
Using a grace period that is too small may bias ASHA too strongly towards
fast converging trials that do not lead to best results at convergence (stagglers). To
overcome this, you can increase the number of brackets, which increases the amount of
resource required for optimisation but decreases the bias towards stragglers.
Default: 1

repetitions: int
Number of execution of ASHA. Default is np.inf which means to
run ASHA until no new trials can be suggested.

Methods

compute_bracket_idx(num)

suggest(num)

Suggest a number of new sets of parameters.

create_bracket

sample

suggest(num: int) → list[Trial][source]¶

Suggest a number of new sets of parameters.

Sample new points until first rung is filled. Afterwards
waits for all trials to be completed before promoting trials
to the next rung.

Parameters

num: int, optional
Number of points to suggest. Defaults to 1.

Returns

list of orion.core.worker.trial:Trial or None
A list of trials suggested by the algorithm. The algorithm may opt out if it cannot make
a good suggestion at the moment (it may be waiting for other trials to complete), in
which case it will return None.

class orion.algo.asha.ASHABracket(owner: ASHA, budgets: list[BudgetTuple], repetition_id: int)[source]¶

Bracket of rungs for the algorithm ASHA.

Parameters

asha: `ASHA` algorithm
The asha algorithm object which this bracket will be part of.

budgets: list of tuple
Each tuple gives the (n_trials, resource_budget) for the respective rung.

repetition_id: int
The id of hyperband execution this bracket belongs to

Attributes

is_filled
ASHA’s first rung can always sample new trials

Methods

get_candidates(rung_id)

Get a candidate for promotion

is_ready([rung_id])

ASHA's always ready for promotions

promote(num)

Promote the first candidate that is found and return it

get_candidates(rung_id: int) → list[Trial][source]¶

Get a candidate for promotion

Raises

TypeError
If get_candidates is called before the entire rung is completed.

property is_filled: bool¶

ASHA’s first rung can always sample new trials

is_ready(rung_id: int | None = None) → bool[source]¶

ASHA’s always ready for promotions

promote(num: int) → list[Trial][source]¶

Promote the first candidate that is found and return it

The rungs are iterated over in reversed order, so that high rungs
are prioritised for promotions. When a candidate is promoted, the loop is broken and
the method returns the promoted trial.

Note

All trials are part of the rungs, for any state. Only completed trials
are eligible for promotion, i.e., only completed trials can be part of top-k.
Lookup for promotion in rung l + 1 contains trials of any status.

orion.algo.asha.compute_budgets(min_resources: float, max_resources: float, reduction_factor: int, num_rungs: int, num_brackets: int)[source]¶

Compute the budgets used for ASHA

        Next 

         Previous

        © Copyright 2017-2022, Epistímio

          Revision f485f624.

  Built with Sphinx using a theme provided by Read the Docs.