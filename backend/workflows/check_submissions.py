"""Temporal workflow for checking submissions and displaying countdown."""

from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        check_for_pending_submissions,
        switch_obs_scene,
        update_countdown_text,
        visit_gallery_activity,
    )


@workflow.defn
class CheckSubmissionsWorkflow:
    """
    Workflow for checking submissions and managing OBS scenes.

    This workflow implements the waiting/screensaver functionality:
    1. Switches to screensaver scene
    2. Checks for pending submissions
    3. If found: Switches to main scene and starts CreateArtworkWorkflow
    4. If not found: Displays 60-second countdown, then repeats
    5. Loops indefinitely until a submission is found

    This workflow is designed to run continuously, creating a dynamic
    livestream experience with countdown timers between artworks.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL
        continuous: Whether to continue with continuous mode after artwork creation

    Returns:
        dict: Dictionary containing:
            - submission_id: ID of the submission that was found
            - artwork_workflow_id: ID of the CreateArtworkWorkflow that was started
    """

    @workflow.run
    async def run(self, cdp_url: str, continuous: bool = False) -> dict:
        workflow.logger.info("Starting CheckSubmissionsWorkflow")
        workflow.logger.info(f"CDP URL: {cdp_url}")

        # Import here to avoid circular dependency issues
        with workflow.unsafe.imports_passed_through():
            from workflows.activities import OBS_MAIN_SCENE, OBS_SCREENSAVER_SCENE

        # Loop indefinitely until we find a submission
        loop_count = 0
        while True:
            loop_count += 1
            workflow.logger.info(f"Submission check loop #{loop_count}")

            # Switch to main scene and show gallery at the start of each check
            await workflow.execute_activity(
                switch_obs_scene,
                args=[OBS_MAIN_SCENE],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow.logger.info(f"✓ Switched to main scene: {OBS_MAIN_SCENE}")

            # Visit gallery homepage for 5 seconds (shows on livestream)
            await workflow.execute_activity(
                visit_gallery_activity,
                args=[cdp_url],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow.logger.info("✓ Gallery homepage displayed")

            # Check for pending submissions
            submission = await workflow.execute_activity(
                check_for_pending_submissions,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            if submission:
                # Found a submission!
                workflow.logger.info(f"✓ Found submission: {submission['id']}")

                # Start CreateArtworkWorkflow
                workflow.logger.info("Starting CreateArtworkWorkflow...")

                # Import Client here to start the artwork workflow
                with workflow.unsafe.imports_passed_through():
                    from temporalio.client import Client
                    import time

                # We need to use an activity to start the next workflow
                # Create a new activity for this purpose
                with workflow.unsafe.imports_passed_through():
                    from workflows.activities import TEMPORAL_HOST, TASK_QUEUE

                # Generate workflow ID
                timestamp = int(workflow.now().timestamp())
                artwork_workflow_id = f"claude-draws-{timestamp}"

                # Start the artwork workflow using execute_local_activity
                # Actually, we should create an activity for this - let me use a child workflow instead

                # Start child workflow for artwork creation
                # Pass the submission ID so CreateArtworkWorkflow knows which submission to process
                artwork_result = await workflow.execute_child_workflow(
                    "CreateArtworkWorkflow",
                    args=[cdp_url, continuous, submission["id"]],
                    id=artwork_workflow_id,
                    task_queue="claude-draws-queue",
                    retry_policy=RetryPolicy(
                        maximum_attempts=0 if continuous else 3,  # Infinite retries in continuous mode
                        backoff_coefficient=2.0,
                    ),
                )

                workflow.logger.info(f"✓ CreateArtworkWorkflow completed: {artwork_workflow_id}")
                workflow.logger.info(f"  Artwork URL: {artwork_result['artwork_url']}")

                # If continuous mode, start a new CheckSubmissionsWorkflow
                if continuous:
                    workflow.logger.info("Continuous mode: starting new CheckSubmissionsWorkflow...")

                    # Start new check workflow as child
                    new_check_workflow_id = f"check-submissions-{int(workflow.now().timestamp())}"

                    # Don't await - let it run independently
                    workflow.start_child_workflow(
                        "CheckSubmissionsWorkflow",
                        args=[cdp_url, continuous],
                        id=new_check_workflow_id,
                        task_queue="claude-draws-queue",
                    )

                    workflow.logger.info(f"✓ Started new CheckSubmissionsWorkflow: {new_check_workflow_id}")

                # Return result
                return {
                    "submission_id": submission["id"],
                    "artwork_workflow_id": artwork_workflow_id,
                    "artwork_url": artwork_result["artwork_url"],
                }

            else:
                # No submission found - switch to screensaver and show countdown
                workflow.logger.info("No submissions found, switching to screensaver...")

                # Switch to screensaver scene
                await workflow.execute_activity(
                    switch_obs_scene,
                    args=[OBS_SCREENSAVER_SCENE],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                workflow.logger.info(f"✓ Switched to screensaver scene: {OBS_SCREENSAVER_SCENE}")

                # Countdown from 60 to 0
                workflow.logger.info("Starting 60-second countdown...")
                for seconds_remaining in range(60, 0, -1):
                    # Update countdown text in OBS
                    await workflow.execute_activity(
                        update_countdown_text,
                        args=[seconds_remaining],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                    # Sleep for 1 second
                    await workflow.sleep(timedelta(seconds=1))

                workflow.logger.info("✓ Countdown complete, checking for submissions again...")
