"""Temporal workflow for checking submissions and displaying countdown."""

from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
with workflow.unsafe.imports_passed_through():
    from workflows.activities import (
        check_for_pending_submissions,
        check_inactivity_and_stop_streaming,
        ensure_obs_streaming,
        switch_obs_scene,
        update_countdown_text,
        visit_gallery_activity,
    )


@workflow.defn
class CheckSubmissionsWorkflow:
    """
    Workflow for checking submissions and managing OBS scenes.

    This workflow performs a single check cycle:
    1. Switches to main scene and shows gallery
    2. Checks for pending submissions
    3. If found: Starts CreateArtworkWorkflow and waits for completion
    4. If not found (continuous mode): Displays 60-second countdown
    5. In continuous mode: Uses continue_as_new to reset workflow history

    This workflow uses continue_as_new in continuous mode to prevent workflow
    history growth while creating a dynamic livestream experience with countdown
    timers between artworks. The workflow history is reset after each check cycle.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL
        continuous: Whether to continue checking for submissions indefinitely

    Returns:
        dict: Dictionary containing:
            - submission_id: ID of the submission that was found (if any)
            - artwork_workflow_id: ID of the CreateArtworkWorkflow that was started (if submission found)
            - artwork_url: URL of the artwork (if submission found)

        Note: In continuous mode, this return value is only reached if the workflow
        is terminated externally, as continue_as_new restarts the workflow.
    """

    @workflow.run
    async def run(self, cdp_url: str, continuous: bool = False) -> dict:
        workflow.logger.info("Starting CheckSubmissionsWorkflow")
        workflow.logger.info(f"CDP URL: {cdp_url}")
        workflow.logger.info(f"Continuous mode: {continuous}")

        # Import here to avoid circular dependency issues
        with workflow.unsafe.imports_passed_through():
            from workflows.activities import OBS_MAIN_SCENE, OBS_SCREENSAVER_SCENE

        # Switch to main scene and show gallery
        await workflow.execute_activity(
            switch_obs_scene,
            args=[OBS_MAIN_SCENE],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        workflow.logger.info(f"✓ Switched to main scene: {OBS_MAIN_SCENE}")

        # Ensure OBS is streaming (may need to restart after wake from sleep)
        await workflow.execute_activity(
            ensure_obs_streaming,
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        workflow.logger.info("✓ OBS streaming confirmed")

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

            # Generate workflow ID
            timestamp = int(workflow.now().timestamp())
            artwork_workflow_id = f"claude-draws-{timestamp}"

            # Start child workflow for artwork creation
            # Pass the submission ID so CreateArtworkWorkflow knows which submission to process
            # Note: We pass continuous=False to CreateArtworkWorkflow since CheckSubmissionsWorkflow
            # handles the continuous mode logic
            artwork_result = await workflow.execute_child_workflow(
                "CreateArtworkWorkflow",
                args=[cdp_url, False, submission["id"]],
                id=artwork_workflow_id,
                task_queue="claude-draws-queue",
                retry_policy=RetryPolicy(
                    maximum_attempts=0 if continuous else 3,  # Infinite retries in continuous mode
                    backoff_coefficient=2.0,
                ),
            )

            workflow.logger.info(f"✓ CreateArtworkWorkflow completed: {artwork_workflow_id}")
            workflow.logger.info(f"  Artwork URL: {artwork_result['artwork_url']}")

            # If continuous mode, use continue_as_new to reset workflow history
            if continuous:
                workflow.logger.info("Continuous mode: resetting workflow history with continue_as_new...")
                workflow.continue_as_new(args=[cdp_url, continuous])

            # Return result (only reached if not continuous mode)
            return {
                "submission_id": submission["id"],
                "artwork_workflow_id": artwork_workflow_id,
                "artwork_url": artwork_result["artwork_url"],
            }

        else:
            # No submission found
            workflow.logger.info("No submissions found")

            if continuous:
                # In continuous mode: show screensaver countdown then schedule next check
                workflow.logger.info("Switching to screensaver...")

                # Switch to screensaver scene
                await workflow.execute_activity(
                    switch_obs_scene,
                    args=[OBS_SCREENSAVER_SCENE],
                    start_to_close_timeout=timedelta(seconds=15),
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
                        start_to_close_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                    # Sleep for 1 second
                    await workflow.sleep(timedelta(seconds=1))

                workflow.logger.info("✓ Countdown complete")

                # Check for inactivity and stop streaming if idle
                # This allows Windows to sleep (OBS streaming blocks sleep)
                streaming_stopped = await workflow.execute_activity(
                    check_inactivity_and_stop_streaming,
                    args=[15],  # 15 minutes inactivity threshold
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

                if streaming_stopped:
                    workflow.logger.info("✓ OBS streaming stopped due to inactivity")
                    workflow.logger.info("Waiting 60 seconds to allow PC to enter sleep mode...")
                    # Give PowerShell sleep monitor time to trigger Windows sleep
                    # The workflow will resume here after PC wakes from sleep
                    await workflow.sleep(timedelta(seconds=60))
                    workflow.logger.info("✓ Sleep window complete - resuming workflow")

                # Use continue_as_new to reset workflow history
                workflow.logger.info("Resetting workflow history with continue_as_new...")
                workflow.continue_as_new(args=[cdp_url, continuous])

            else:
                # Not continuous mode: just return
                workflow.logger.info("Not in continuous mode, workflow complete")
                return {
                    "submission_id": None,
                    "artwork_workflow_id": None,
                    "artwork_url": None,
                }
