# Product Definition

## Product Name

YouTube Factory

## Problem

Creating a consistent stream of high-quality short-form video content requires repeated work across research, writing, voice production, asset creation, editing, publishing, and analytics.

Most AI content automation approaches optimize for volume rather than quality, originality, or learning from performance.

## Product Goal

Build a platform that automates repetitive production work while maintaining:

- factual quality
- content originality
- human review
- consistent visual standards
- measurable experiments
- provider flexibility

## Initial User

The initial user is the project owner operating one Spanish YouTube Shorts channel.

## Initial Content Niche

Engineering, technology, infrastructure, and everyday technical curiosities.

## MVP User Story

As the channel operator, I want to provide a topic and receive a fully rendered vertical Short so that I can review it before deciding whether to publish it.

## MVP Input

A topic string.

Example:

> Por qué las tapas de alcantarilla son redondas

## MVP Output

A project folder containing structured intermediate artifacts and `final.mp4`.

## MVP Success Criteria

The pipeline:

- can be run locally
- generates structured artifacts
- validates model output
- produces narration
- produces scene assets
- creates subtitles
- renders a valid vertical MP4
- allows manual inspection of every stage

The resulting video should be coherent enough that the operator would realistically consider publishing it.

## Product Principles

### Quality before scale

Do not optimize for number of generated videos before the output format is good.

### Automation with control

Automate repeatable work but preserve approval before publication.

### Data over intuition

Later product decisions should be informed by analytics and structured experiments.

### Config-driven future

The long-term platform should support multiple channels without duplicating code.

## Future Capabilities

- topic discovery
- automated trend research
- multiple content formats
- multiple languages
- approval workflows
- scheduled publishing
- YouTube analytics ingestion
- experiment tracking
- content performance scoring
- multi-channel orchestration

## Non-Goals For MVP

- fully autonomous channel operation
- mass publishing
- advanced SaaS UI
- multi-user accounts
- production cloud infrastructure
- Kubernetes
