import akka.actor.{Actor, ActorRef, ActorSystem, Props}
import akka.http.scaladsl.Http
import akka.http.scaladsl.marshallers.sprayjson.SprayJsonSupport
import akka.http.scaladsl.server.Directives._
import akka.pattern.ask
import akka.util.Timeout
import spray.json.DefaultJsonProtocol
import akka.http.scaladsl.model.StatusCodes
import scala.util.{Success, Failure}

import scala.concurrent.Future
import scala.concurrent.duration._

class BackgroundTaskActor extends Actor {
  // Define the states and messages for the background task
  var isRunning = false
  var progress = 0
  var taskStatusReceiver: Option[ActorRef] = None

  override def receive: Receive = {
    case StartTask =>
      isRunning = true
      taskStatusReceiver = Some(sender())
      performTask()

    case GetTaskStatus =>
      taskStatusReceiver = Some(sender())
      sendTaskStatus()

    case TaskCompleted =>
      isRunning = false
      sendTaskStatus()
      taskStatusReceiver = None
  }

  private def performTask(): Unit = {
    // Simulate a long-running task
    for (i <- 1 to 10) {
      Thread.sleep(10000)
      progress = i * 10
      sendTaskStatus()
    }

    self ! TaskCompleted
  }

  private def sendTaskStatus(): Unit = {
    taskStatusReceiver.foreach(ref => ref ! TaskStatus(isRunning, progress))
  }
}
// Step 2: Start the background task
case object StartTask
case object TaskCompleted
case object GetCurrentTaskStatus
// Step 3: Implement the web hook endpoint
case object GetTaskStatus
case class TaskStatus(isRunning: Boolean, progress: Int)

// Step 4: JSON Marshalling
trait JsonSupport extends SprayJsonSupport with DefaultJsonProtocol {
  implicit val taskStatusFormat = jsonFormat2(TaskStatus)
}

class TaskStatusActor extends Actor {
  private var currentTaskStatus: TaskStatus = TaskStatus(isRunning = false, progress = 0)

  override def receive: Receive = {
    case GetCurrentTaskStatus =>
      sender() ! currentTaskStatus

    case taskStatus: TaskStatus =>
      currentTaskStatus = taskStatus
  }
}

object WebService extends JsonSupport {
  def main(args: Array[String]): Unit = {
    implicit val system = ActorSystem("web-service")
    implicit val timeout: Timeout = Timeout(5.seconds)
    implicit val executionContext = system.dispatcher

    val backgroundTaskActor = system.actorOf(Props[BackgroundTaskActor], "background-task-actor")

    val route =
      path("start-task") {
        post {
          // Start the background task
          backgroundTaskActor ! StartTask
          complete("Background task started")
        }
      } ~
        path("task-status") {
          get {
            val taskStatusActor = system.actorOf(Props[TaskStatusActor])
            onComplete((taskStatusActor ? GetCurrentTaskStatus).mapTo[TaskStatus]) {
              case Success(taskStatus) =>
                complete(taskStatus)
              case Failure(ex) =>
                // Handle the failure case
                complete(StatusCodes.InternalServerError, "Failed to retrieve task status")
            }
          }
        }

    Http().newServerAt("localhost", 8080).bind(route)
  }
}
