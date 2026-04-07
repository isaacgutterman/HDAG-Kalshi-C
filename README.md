# Kalshi Pipeline

Professional Python scaffold for Team 3, Case 3: Model-Driven Directional Edge.

## Purpose

This repository will hold an authenticated Kalshi data-ingestion pipeline for:

- real-time market data collection
- historical market data collection
- local storage for backtesting
- live strategy data access

## Project Structure

- `app/ingest/` - ingestion-layer package
- `app/storage/` - storage-layer package
- `app/services/` - shared service integrations
- `scripts/` - operator and utility scripts
- `tests/` - automated tests
- `data/` - local data artifacts (git-ignored except placeholder)

## Setup

Setup instructions will be added in the next steps.

## Environment

Copy `.env.example` to `.env` and fill in project-specific secrets and configuration.

## Status

Initial project scaffold only. No business logic has been added yet.
